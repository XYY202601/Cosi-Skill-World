from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import uuid4

from providers import summarize_prompt_context


DEFAULT_SKILL_ID = "mr_visit_jp"
DEFAULT_CAPABILITY_ID = "practice_session"
DEFAULT_LOCALE = "ja-JP"


def _normalize_string(value: Any, *, fallback: str = "") -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return fallback


def _normalize_optional_string(value: Any) -> str | None:
    normalized = _normalize_string(value)
    return normalized or None


def _normalize_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    normalized: list[str] = []
    for item in value:
        candidate = _normalize_string(item)
        if candidate:
            normalized.append(candidate)
    return tuple(normalized)


def _normalize_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return deepcopy(value)


def _derive_trace_id(session_id: str, raw_trace_id: str | None = None) -> str:
    trace_id = _normalize_string(raw_trace_id)
    if trace_id:
        return trace_id
    normalized_session_id = _normalize_string(session_id)
    if normalized_session_id:
        return f"trace_{normalized_session_id}"
    return f"trace_{uuid4().hex[:12]}"


def _continuity_metadata(continuity_context: dict[str, Any]) -> dict[str, Any]:
    suggested_focus_subskills = [
        item
        for item in continuity_context.get("suggested_focus_subskills", [])
        if isinstance(item, str) and item.strip()
    ]
    carryover_focus_subskills = [
        item
        for item in continuity_context.get("carryover_focus_subskills", [])
        if isinstance(item, str) and item.strip()
    ]
    next_actions = [
        item.strip()
        for item in continuity_context.get("next_actions", [])
        if isinstance(item, str) and item.strip()
    ]
    teaching_plan_snapshot = continuity_context.get("teaching_plan_snapshot", {})
    snapshot_metadata = (
        {
            "snapshot_id": _normalize_optional_string(teaching_plan_snapshot.get("snapshot_id")),
            "plan_version": teaching_plan_snapshot.get("plan_version"),
            "frozen_at": _normalize_optional_string(teaching_plan_snapshot.get("frozen_at")),
        }
        if isinstance(teaching_plan_snapshot, dict)
        else None
    )
    return {
        "summary": _normalize_string(continuity_context.get("summary")),
        "suggested_focus_subskills": suggested_focus_subskills,
        "carryover_focus_subskills": carryover_focus_subskills,
        "next_actions": next_actions,
        "teaching_plan_snapshot": snapshot_metadata,
    }


def build_turn_id(session_id: str, turn_index: int) -> str:
    return f"{session_id}:turn:{turn_index:04d}"


@dataclass
class DomainSessionContext:
    skill_id: str
    capability_id: str
    action_id: str
    session_id: str
    learner_id: str
    scenario_id: str
    persona_id: str
    prompt_profile: str
    experiment_id: str | None = None
    locale: str = DEFAULT_LOCALE
    trace_id: str = ""
    turn_id: str | None = None
    prompt_flags: tuple[str, ...] = field(default_factory=tuple)
    continuity_context: dict[str, Any] = field(default_factory=dict)
    org_id: str | None = None

    def __post_init__(self) -> None:
        self.skill_id = _normalize_string(self.skill_id, fallback=DEFAULT_SKILL_ID)
        self.capability_id = _normalize_string(
            self.capability_id,
            fallback=DEFAULT_CAPABILITY_ID,
        )
        self.action_id = _normalize_string(self.action_id, fallback="unknown_action")
        self.session_id = _normalize_string(self.session_id)
        self.learner_id = _normalize_string(self.learner_id)
        self.scenario_id = _normalize_string(self.scenario_id)
        self.persona_id = _normalize_string(self.persona_id)
        self.prompt_profile = _normalize_string(self.prompt_profile, fallback="unknown")
        self.experiment_id = _normalize_optional_string(self.experiment_id)
        self.locale = _normalize_string(self.locale, fallback=DEFAULT_LOCALE)
        self.trace_id = _derive_trace_id(self.session_id, self.trace_id)
        self.turn_id = _normalize_optional_string(self.turn_id)
        self.prompt_flags = _normalize_string_list(self.prompt_flags)
        self.continuity_context = _normalize_object(self.continuity_context)
        self.org_id = _normalize_optional_string(self.org_id)

    @classmethod
    def from_session_seed(
        cls,
        *,
        session_id: str,
        learner_id: str,
        scenario_id: str,
        persona_id: str,
        prompt_context: dict[str, Any] | None,
        continuity_context: dict[str, Any] | None = None,
        skill_id: str = DEFAULT_SKILL_ID,
        capability_id: str = DEFAULT_CAPABILITY_ID,
        action_id: str = "start_session",
        locale: str = DEFAULT_LOCALE,
        trace_id: str | None = None,
        org_id: str | None = None,
    ) -> DomainSessionContext:
        prompt_summary = summarize_prompt_context(prompt_context)
        return cls(
            skill_id=skill_id,
            capability_id=capability_id,
            action_id=action_id,
            session_id=session_id,
            learner_id=learner_id,
            scenario_id=scenario_id,
            persona_id=persona_id,
            prompt_profile=str(prompt_summary["profile_id"]),
            experiment_id=prompt_summary.get("experiment_id"),
            locale=locale,
            trace_id=trace_id or "",
            turn_id=None,
            prompt_flags=tuple(prompt_summary.get("flags", [])),
            continuity_context=_normalize_object(continuity_context),
            org_id=org_id,
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DomainSessionContext:
        return cls(
            skill_id=str(payload.get("skill_id", DEFAULT_SKILL_ID)),
            capability_id=str(payload.get("capability_id", DEFAULT_CAPABILITY_ID)),
            action_id=str(payload.get("action_id", "get_session")),
            session_id=str(payload.get("session_id", "")),
            learner_id=str(payload.get("learner_id", "")),
            scenario_id=str(payload.get("scenario_id", "")),
            persona_id=str(payload.get("persona_id", "")),
            prompt_profile=str(payload.get("prompt_profile", "unknown")),
            experiment_id=payload.get("experiment_id"),
            locale=str(payload.get("locale", DEFAULT_LOCALE)),
            trace_id=str(payload.get("trace_id", "")),
            turn_id=payload.get("turn_id"),
            prompt_flags=tuple(payload.get("prompt_flags", [])),
            continuity_context=_normalize_object(payload.get("continuity_context")),
            org_id=payload.get("org_id"),
        )

    @classmethod
    def from_legacy_session_payload(cls, payload: dict[str, Any]) -> DomainSessionContext:
        return cls.from_session_seed(
            skill_id=str(payload.get("skill_id", DEFAULT_SKILL_ID)),
            session_id=str(payload.get("session_id", "")),
            learner_id=str(payload.get("learner_id", "")),
            scenario_id=str(payload.get("scenario_id", "")),
            persona_id=str(payload.get("persona_id", "")),
            prompt_context=_normalize_object(payload.get("prompt_context")),
            continuity_context=_normalize_object(payload.get("continuity_context")),
            capability_id=str(payload.get("capability_id", DEFAULT_CAPABILITY_ID)),
            action_id=str(payload.get("action_id", "get_session")),
            locale=str(payload.get("locale", DEFAULT_LOCALE)),
            trace_id=str(payload.get("trace_id", "")),
        )

    def for_action(
        self,
        action_id: str,
        *,
        capability_id: str | None = None,
        turn_id: str | None = None,
    ) -> DomainSessionContext:
        return replace(
            self,
            action_id=action_id,
            capability_id=capability_id or self.capability_id,
            turn_id=turn_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "capability_id": self.capability_id,
            "action_id": self.action_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "learner_id": self.learner_id,
            "scenario_id": self.scenario_id,
            "persona_id": self.persona_id,
            "prompt_profile": self.prompt_profile,
            "experiment_id": self.experiment_id,
            "prompt_flags": list(self.prompt_flags),
            "locale": self.locale,
            "trace_id": self.trace_id,
            "continuity_context": _normalize_object(self.continuity_context),
            "org_id": self.org_id,
        }

    def metadata_payload(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "capability_id": self.capability_id,
            "action_id": self.action_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "learner_id": self.learner_id,
            "scenario_id": self.scenario_id,
            "persona_id": self.persona_id,
            "prompt_profile": self.prompt_profile,
            "experiment_id": self.experiment_id,
            "prompt_flags": list(self.prompt_flags),
            "locale": self.locale,
            "trace_id": self.trace_id,
            "continuity": _continuity_metadata(self.continuity_context),
        }

    def attach_to_event_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        metadata.update(self.metadata_payload())
        return metadata

    def attach_to_review_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        metadata.update(self.metadata_payload())
        return metadata
