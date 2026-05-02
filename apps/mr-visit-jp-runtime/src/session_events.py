from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from runtime_context import (
    DEFAULT_CAPABILITY_ID,
    DEFAULT_SKILL_ID,
    DomainSessionContext,
    build_turn_id,
)


EVENT_SCHEMA_VERSION = "1.1"
DEFAULT_EVENT_SOURCE = "runtime"
ENVELOPE_TOP_LEVEL_FIELDS = frozenset(
    {
        "type",
        "source",
        "stage",
        "content",
        "metadata",
        "skill_id",
        "session_id",
        "turn_id",
        "seq",
        "timestamp",
        "schema_version",
    }
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _event_schema() -> dict[str, Any]:
    path = (
        _repo_root()
        / "packages"
        / "shared-schemas"
        / "schemas"
        / "session_event_envelope.schema.json"
    )
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return payload


def _normalize_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return deepcopy(value)


def _normalize_string(value: Any, *, fallback: str = "") -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return fallback


def _normalize_optional_string(value: Any) -> str | None:
    normalized = _normalize_string(value)
    return normalized or None


def _infer_stage(payload: dict[str, Any], metadata: dict[str, Any]) -> str:
    explicit_stage = _normalize_string(payload.get("stage"))
    if explicit_stage:
        return explicit_stage
    capability_id = _normalize_string(metadata.get("capability_id"))
    if capability_id:
        return capability_id
    return DEFAULT_CAPABILITY_ID


def _normalize_content(payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("content")
    if isinstance(content, dict):
        return deepcopy(content)
    return {
        key: deepcopy(value)
        for key, value in payload.items()
        if key not in ENVELOPE_TOP_LEVEL_FIELDS and key not in {"skill_id", "session_id", "turn_id"}
    }


def _normalize_metadata(
    payload: dict[str, Any],
    *,
    session_id: str,
    skill_id: str,
    turn_id: str | None,
) -> dict[str, Any]:
    metadata = _normalize_object(payload.get("metadata"))
    metadata.setdefault("skill_id", skill_id)
    metadata.setdefault("session_id", session_id)
    if turn_id is not None:
        metadata.setdefault("turn_id", turn_id)

    for field in (
        "capability_id",
        "action_id",
        "learner_id",
        "scenario_id",
        "persona_id",
        "prompt_profile",
        "experiment_id",
        "locale",
        "trace_id",
        "continuity",
        "prompt_flags",
    ):
        if field in payload and field not in metadata:
            metadata[field] = deepcopy(payload[field])

    if "trace_id" not in metadata and session_id:
        metadata["trace_id"] = f"trace_{session_id}"
    return metadata


def _normalize_seq(raw_seq: Any, inferred_seq: int) -> int:
    if isinstance(raw_seq, int) and raw_seq > 0:
        return raw_seq
    return inferred_seq


def _normalize_turn_id(
    payload: dict[str, Any],
    *,
    session_id: str,
    metadata: dict[str, Any],
) -> str | None:
    turn_id = _normalize_optional_string(payload.get("turn_id"))
    if turn_id is None:
        turn_id = _normalize_optional_string(metadata.get("turn_id"))
    if turn_id is not None:
        return turn_id
    turn_index = payload.get("turn_index")
    if isinstance(turn_index, int) and turn_index > 0 and session_id:
        return build_turn_id(session_id, turn_index)
    return None


@dataclass(frozen=True)
class SessionEventEnvelope:
    type: str
    source: str
    stage: str
    content: dict[str, Any]
    metadata: dict[str, Any]
    skill_id: str
    session_id: str
    turn_id: str | None
    seq: int
    timestamp: str
    schema_version: str = EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "type": self.type,
            "source": self.source,
            "stage": self.stage,
            "content": deepcopy(self.content),
            "metadata": deepcopy(self.metadata),
            "skill_id": self.skill_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "seq": self.seq,
            "timestamp": self.timestamp,
            "schema_version": self.schema_version,
        }
        validate_session_event_payload(payload)
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        fallback_session_id: str | None = None,
        inferred_seq: int = 1,
    ) -> SessionEventEnvelope:
        if not isinstance(payload, dict):
            raise ValueError("Session event payload must be an object")

        session_id = _normalize_string(
            payload.get("session_id"),
            fallback=_normalize_string(fallback_session_id),
        )
        raw_skill_id = payload.get("skill_id")
        metadata_seed = _normalize_object(payload.get("metadata"))
        skill_id = _normalize_string(
            raw_skill_id,
            fallback=_normalize_string(metadata_seed.get("skill_id"), fallback=DEFAULT_SKILL_ID),
        )
        turn_id = _normalize_turn_id(payload, session_id=session_id, metadata=metadata_seed)
        metadata = _normalize_metadata(
            payload,
            session_id=session_id,
            skill_id=skill_id,
            turn_id=turn_id,
        )
        envelope = cls(
            type=_normalize_string(payload.get("type")),
            source=_normalize_string(payload.get("source"), fallback=DEFAULT_EVENT_SOURCE),
            stage=_infer_stage(payload, metadata),
            content=_normalize_content(payload),
            metadata=metadata,
            skill_id=skill_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=_normalize_seq(payload.get("seq"), inferred_seq),
            timestamp=_normalize_string(payload.get("timestamp")),
            schema_version=_normalize_string(
                payload.get("schema_version"),
                fallback=EVENT_SCHEMA_VERSION,
            ),
        )
        validate_session_event_payload(envelope.to_dict())
        return envelope


def validate_session_event_payload(payload: dict[str, Any]) -> None:
    validator = Draft202012Validator(_event_schema())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "<root>"
        raise ValueError(f"Session event envelope failed schema validation at {path}: {first.message}")


def build_session_event_envelope(
    *,
    event_type: str,
    timestamp: str,
    session_context: DomainSessionContext,
    content: dict[str, Any] | None = None,
    source: str = DEFAULT_EVENT_SOURCE,
    stage: str | None = None,
    seq: int | None = None,
) -> SessionEventEnvelope:
    return SessionEventEnvelope(
        type=event_type,
        source=source,
        stage=stage or session_context.capability_id,
        content=_normalize_object(content),
        metadata=session_context.metadata_payload(),
        skill_id=session_context.skill_id,
        session_id=session_context.session_id,
        turn_id=session_context.turn_id,
        seq=seq or 1,
        timestamp=timestamp,
        schema_version=EVENT_SCHEMA_VERSION,
    )


def build_session_event_payload(
    *,
    event_type: str,
    timestamp: str,
    session_context: DomainSessionContext,
    content: dict[str, Any] | None = None,
    source: str = DEFAULT_EVENT_SOURCE,
    stage: str | None = None,
    seq: int | None = None,
) -> dict[str, Any]:
    payload = {
        "type": event_type,
        "source": source,
        "stage": stage or session_context.capability_id,
        "content": _normalize_object(content),
        "metadata": session_context.metadata_payload(),
        "skill_id": session_context.skill_id,
        "session_id": session_context.session_id,
        "turn_id": session_context.turn_id,
        "timestamp": timestamp,
        "schema_version": EVENT_SCHEMA_VERSION,
    }
    if seq is not None:
        payload["seq"] = seq
    return payload


def normalize_session_event_payload(
    payload: dict[str, Any],
    *,
    fallback_session_id: str | None = None,
    inferred_seq: int = 1,
) -> dict[str, Any]:
    return SessionEventEnvelope.from_dict(
        payload,
        fallback_session_id=fallback_session_id,
        inferred_seq=inferred_seq,
    ).to_dict()


def sort_envelopes_for_replay(
    envelopes: list[SessionEventEnvelope],
) -> list[SessionEventEnvelope]:
    return sorted(
        envelopes,
        key=lambda envelope: (envelope.seq, envelope.timestamp, envelope.type),
    )


def normalize_session_event_payloads(
    payloads: list[dict[str, Any]],
    *,
    fallback_session_id: str | None = None,
) -> list[dict[str, Any]]:
    prepared: list[tuple[SessionEventEnvelope, bool]] = [
        (
            SessionEventEnvelope.from_dict(
                payload,
                fallback_session_id=fallback_session_id,
                inferred_seq=index,
            ),
            isinstance(payload.get("seq"), int) and int(payload["seq"]) > 0,
        )
        for index, payload in enumerate(payloads, start=1)
    ]
    if all(has_explicit_seq for _, has_explicit_seq in prepared):
        ordered = sort_envelopes_for_replay([envelope for envelope, _ in prepared])
        return [envelope.to_dict() for envelope in ordered]

    ordered = sorted(
        [envelope for envelope, _ in prepared],
        key=lambda envelope: (envelope.timestamp, envelope.seq, envelope.type),
    )
    resequenced = [
        replace(envelope, seq=index)
        for index, envelope in enumerate(ordered, start=1)
    ]
    return [envelope.to_dict() for envelope in resequenced]
