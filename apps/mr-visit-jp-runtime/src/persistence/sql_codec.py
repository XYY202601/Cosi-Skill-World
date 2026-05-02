from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from typing import Any

from providers import summarize_prompt_context


DEFAULT_SQL_SKILL_ID = "mr_visit_jp"
DEFAULT_SQL_LOCALE = "ja-JP"


def normalize_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if candidate:
            normalized.append(candidate)
    return normalized


def normalize_datetime(value: Any, *, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            if candidate.endswith("Z"):
                candidate = candidate[:-1] + "+00:00"
            parsed = datetime.fromisoformat(candidate)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    if fallback is not None:
        return fallback
    return datetime.now(tz=UTC)


def canonical_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_locale_from_session_payload(payload: dict[str, Any]) -> str:
    context = payload.get("context", {})
    if isinstance(context, dict):
        locale = context.get("locale")
        if isinstance(locale, str) and locale.strip():
            return locale.strip()
    locale = payload.get("locale")
    if isinstance(locale, str) and locale.strip():
        return locale.strip()
    return DEFAULT_SQL_LOCALE


def derive_skill_id_from_session_payload(payload: dict[str, Any]) -> str:
    context = payload.get("context", {})
    if isinstance(context, dict):
        skill_id = context.get("skill_id")
        if isinstance(skill_id, str) and skill_id.strip():
            return skill_id.strip()
    skill_id = payload.get("skill_id")
    if isinstance(skill_id, str) and skill_id.strip():
        return skill_id.strip()
    return DEFAULT_SQL_SKILL_ID


def build_prompt_context_snapshot_row(
    prompt_context: dict[str, Any] | None,
    *,
    created_at: datetime,
    skill_id: str = DEFAULT_SQL_SKILL_ID,
) -> dict[str, Any]:
    raw_context = prompt_context if isinstance(prompt_context, dict) else {}
    summary = summarize_prompt_context(raw_context)
    summary_payload = dict(summary)
    description = raw_context.get("description")
    if isinstance(description, str) and description.strip():
        summary_payload["description"] = description.strip()

    normalized_context = {
        "profile_id": summary["profile_id"],
        "experiment_id": summary.get("experiment_id"),
        "flags": list(summary.get("flags", [])),
        "description": summary_payload.get("description", ""),
        "contracts": raw_context.get("contracts", {}),
    }
    return {
        "context_hash": canonical_json_hash(normalized_context),
        "skill_id": skill_id,
        "prompt_profile": str(summary["profile_id"]),
        "experiment_id": summary.get("experiment_id"),
        "prompt_flags_json": list(summary.get("flags", [])),
        "contracts_json": normalize_object(raw_context.get("contracts")),
        "summary_json": summary_payload,
        "created_at": created_at,
    }


def reconstruct_prompt_context(
    *,
    prompt_profile: str,
    experiment_id: str | None,
    prompt_flags_json: Any,
    contracts_json: Any,
    summary_json: Any,
) -> dict[str, Any]:
    summary = normalize_object(summary_json)
    payload = {
        "profile_id": prompt_profile,
        "experiment_id": experiment_id,
        "flags": normalize_string_list(prompt_flags_json),
        "contracts": normalize_object(contracts_json),
    }
    description = summary.get("description")
    if isinstance(description, str) and description.strip():
        payload["description"] = description.strip()
    return payload


def build_event_row(event: dict[str, Any], *, org_id: str | None = None) -> dict[str, Any]:
    metadata = normalize_object(event.get("metadata"))
    resolved_org_id = str(org_id or "").strip() or "__unscoped__"
    return {
        "session_id": str(event["session_id"]),
        "org_id": resolved_org_id,
        "turn_id": event.get("turn_id"),
        "seq": int(event["seq"]),
        "type": str(event["type"]),
        "source": str(event["source"]),
        "stage": str(event["stage"]),
        "timestamp": normalize_datetime(event["timestamp"]),
        "schema_version": str(event["schema_version"]),
        "skill_id": str(event.get("skill_id", metadata.get("skill_id", DEFAULT_SQL_SKILL_ID))),
        "capability_id": str(metadata.get("capability_id", "")),
        "action_id": str(metadata.get("action_id", "")),
        "learner_id": str(metadata.get("learner_id", "")),
        "scenario_id": str(metadata.get("scenario_id", "")),
        "persona_id": str(metadata.get("persona_id", "")),
        "prompt_profile": str(metadata.get("prompt_profile", "unknown")),
        "experiment_id": (
            str(metadata["experiment_id"])
            if metadata.get("experiment_id") is not None
            else None
        ),
        "trace_id": str(metadata.get("trace_id", f"trace_{event['session_id']}")),
        "content_json": normalize_object(event.get("content")),
        "metadata_json": metadata,
    }


def reconstruct_event_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": str(row["type"]),
        "source": str(row["source"]),
        "stage": str(row["stage"]),
        "content": normalize_object(row.get("content_json")),
        "metadata": normalize_object(row.get("metadata_json")),
        "skill_id": str(row["skill_id"]),
        "session_id": str(row["session_id"]),
        "turn_id": row.get("turn_id"),
        "seq": int(row["seq"]),
        "timestamp": normalize_datetime(row["timestamp"]).isoformat(),
        "schema_version": str(row["schema_version"]),
    }


def build_review_row(
    *,
    session_id: str,
    prompt_context_id: int,
    prompt_context: dict[str, Any] | None,
    review: dict[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    meta = normalize_object(review.get("meta"))
    compliance_flags = review.get("compliance_flags", [])
    compliance_rule_ids: list[str] = []
    compliance_severities: list[str] = []
    if isinstance(compliance_flags, list):
        for item in compliance_flags:
            if not isinstance(item, dict):
                continue
            rule_id = item.get("rule_id")
            severity = item.get("severity")
            if isinstance(rule_id, str) and rule_id.strip():
                compliance_rule_ids.append(rule_id.strip())
            if isinstance(severity, str) and severity.strip():
                compliance_severities.append(severity.strip())

    prompt_summary = summarize_prompt_context(prompt_context if isinstance(prompt_context, dict) else None)
    return {
        "session_id": session_id,
        "prompt_context_id": prompt_context_id,
        "overall_score": int(review.get("overall_score", 0)),
        "overall_band": str(review.get("overall_band", "unknown")),
        "priority_subskills": normalize_string_list(review.get("priority_subskills")),
        "compliance_rule_ids": compliance_rule_ids,
        "compliance_severities": compliance_severities,
        "artifact_sources_json": normalize_object(meta.get("artifact_sources")),
        "fallback_reasons_json": list(meta.get("fallback_reasons", []))
        if isinstance(meta.get("fallback_reasons"), list)
        else [],
        "prompt_profile": str(prompt_summary["profile_id"]),
        "experiment_id": prompt_summary.get("experiment_id"),
        "created_at": created_at,
        "payload_json": review,
    }


def derive_source_session_id_from_progress_payload(payload: dict[str, Any]) -> str | None:
    recent_history = payload.get("recent_history", [])
    if not isinstance(recent_history, list) or not recent_history:
        return None
    latest = recent_history[-1]
    if not isinstance(latest, dict):
        return None
    session_id = latest.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()
    return None


def derive_last_session_at_from_progress_payload(payload: dict[str, Any]) -> datetime | None:
    recent_history = payload.get("recent_history", [])
    if not isinstance(recent_history, list) or not recent_history:
        return None
    latest = recent_history[-1]
    if not isinstance(latest, dict):
        return None
    timestamp = latest.get("timestamp")
    if timestamp is None:
        return None
    return normalize_datetime(timestamp)


def build_progress_snapshot_row(payload: dict[str, Any], *, org_id: str | None = None) -> dict[str, Any]:
    updated_at = normalize_datetime(payload.get("updated_at"))
    resolved_org_id = str(org_id or "").strip() or "__unscoped__"
    return {
        "learner_id": str(payload["learner_id"]),
        "org_id": resolved_org_id,
        "source_session_id": derive_source_session_id_from_progress_payload(payload),
        "total_sessions": int(payload.get("total_sessions", 0)),
        "total_exp": int(payload.get("total_exp", 0)),
        "level": int(payload.get("level", 1)),
        "updated_at": updated_at,
        "subskills_json": normalize_object(payload.get("subskills")),
        "weakness_clusters_json": list(payload.get("weakness_clusters", []))
        if isinstance(payload.get("weakness_clusters"), list)
        else [],
        "recent_history_json": list(payload.get("recent_history", []))
        if isinstance(payload.get("recent_history"), list)
        else [],
        "coach_memory_json": normalize_object(payload.get("coach_memory")),
        "payload_json": payload,
    }


def build_recommendation_rows(
    *,
    progress_snapshot_id: int,
    learner_id: str,
    source_session_id: str | None,
    updated_at: datetime,
    recommendations: Any,
) -> list[dict[str, Any]]:
    if not isinstance(recommendations, list):
        return []
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(recommendations, start=1):
        if not isinstance(item, dict):
            continue
        scenario_id = item.get("scenario_id")
        title = item.get("title")
        difficulty = item.get("difficulty")
        reason = item.get("reason")
        if not all(isinstance(value, str) and value.strip() for value in (scenario_id, title, difficulty, reason)):
            continue
        rows.append(
            {
                "progress_snapshot_id": progress_snapshot_id,
                "learner_id": learner_id,
                "source_session_id": source_session_id,
                "rank": index,
                "scenario_id": scenario_id.strip(),
                "title": title.strip(),
                "difficulty": difficulty.strip(),
                "target_subskills": normalize_string_list(item.get("target_subskills")),
                "reason": reason.strip(),
                "created_at": updated_at,
            }
        )
    return rows
