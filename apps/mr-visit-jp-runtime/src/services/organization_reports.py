from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from persistence.interfaces import SessionStore
from providers import summarize_prompt_context


UNSCOPED_ORGANIZATION_IDS = {"all", "default", "global", "local", "unscoped"}
COMPLIANCE_SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "positive": 0,
}


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _normalize_string(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return ""


def _normalize_optional_string(value: Any) -> str | None:
    normalized = _normalize_string(value)
    return normalized or None


def _string_list(values: Any, *, max_items: int | None = None) -> list[str]:
    if not isinstance(values, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_string(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(normalized)
        if max_items is not None and len(items) >= max_items:
            break
    return items


def _string_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    return None


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _average(values: Iterable[float]) -> float:
    numbers = list(values)
    if not numbers:
        return 0.0
    return round(sum(numbers) / len(numbers), 1)


def _overall_band(review: dict[str, Any], overall_score: int | None) -> str | None:
    raw_value = _normalize_optional_string(review.get("overall_band"))
    if raw_value is not None:
        return raw_value
    if overall_score is None:
        return None
    if overall_score >= 85:
        return "advanced"
    if overall_score >= 72:
        return "proficient"
    if overall_score >= 58:
        return "developing"
    return "emerging"


def _severity_rank(value: str | None) -> int:
    if value is None:
        return -1
    return COMPLIANCE_SEVERITY_RANK.get(value, -1)


def _max_compliance_severity(severities: Iterable[str]) -> str | None:
    candidates = [_normalize_optional_string(item) for item in severities]
    normalized = [item for item in candidates if item is not None]
    if not normalized:
        return None
    return max(normalized, key=lambda item: (_severity_rank(item), item))


def _priority_subskills(review: dict[str, Any], focus_subskills: list[str]) -> list[str]:
    explicit = _string_list(review.get("priority_subskills"), max_items=4)
    if explicit:
        return explicit

    review_subskills = _string_mapping(review.get("subskills"))
    ranked: list[tuple[float, str]] = []
    for subskill_id, payload in review_subskills.items():
        normalized_subskill_id = _normalize_string(subskill_id)
        if not normalized_subskill_id:
            continue
        score = _safe_float(_string_mapping(payload).get("score"))
        if score is None:
            continue
        ranked.append((score, normalized_subskill_id))

    ranked.sort(key=lambda item: (item[0], item[1]))
    derived = [subskill_id for score, subskill_id in ranked if score <= 3.0][:4]
    if derived:
        return derived
    return _string_list(focus_subskills, max_items=3)


def _active_focus_subskills(
    review: dict[str, Any],
    continuity_context: dict[str, Any],
    priority_subskills: list[str],
) -> list[str]:
    coaching_feedback = _string_mapping(review.get("coaching_feedback"))
    collected = [
        *_string_list(coaching_feedback.get("focus_subskills"), max_items=4),
        *_string_list(continuity_context.get("suggested_focus_subskills"), max_items=4),
        *_string_list(continuity_context.get("carryover_focus_subskills"), max_items=4),
        *_string_list(priority_subskills, max_items=4),
    ]
    return _string_list(collected, max_items=4)


def _needs_attention_reasons(
    *,
    average_score: float | None,
    last_score: int | None,
    completion_rate: float,
    highest_compliance_severity: str | None,
    recurring_weaknesses: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []

    if _severity_rank(highest_compliance_severity) >= COMPLIANCE_SEVERITY_RANK["high"]:
        reasons.append(
            {
                "code": "high_compliance_risk",
                "detail": "Recent finalized sessions include high-risk compliance flags.",
                "severity": highest_compliance_severity,
            }
        )
    elif _severity_rank(highest_compliance_severity) >= COMPLIANCE_SEVERITY_RANK["medium"]:
        reasons.append(
            {
                "code": "medium_compliance_risk",
                "detail": "Recent sessions show repeated medium compliance risk.",
                "severity": highest_compliance_severity,
            }
        )

    if average_score is not None and average_score < 70:
        reasons.append(
            {
                "code": "low_average_score",
                "detail": f"Average finalized review score is {average_score:.1f}.",
            }
        )
    elif last_score is not None and last_score < 65:
        reasons.append(
            {
                "code": "low_latest_score",
                "detail": f"Latest finalized review score is {last_score}.",
            }
        )

    if completion_rate < 0.7:
        reasons.append(
            {
                "code": "low_completion_rate",
                "detail": f"Only {round(completion_rate * 100)}% of sessions were finalized.",
            }
        )

    top_weakness = recurring_weaknesses[0] if recurring_weaknesses else None
    if isinstance(top_weakness, dict) and int(top_weakness.get("occurrences", 0)) >= 2:
        reasons.append(
            {
                "code": "recurring_weakness",
                "detail": "A repeated weakness is appearing across recent reviews.",
                "subskill_id": _normalize_optional_string(top_weakness.get("subskill_id")),
            }
        )

    return reasons


def _session_org_id(payload: dict[str, Any]) -> str | None:
    context = _string_mapping(payload.get("context"))
    return _normalize_optional_string(context.get("org_id"))


@dataclass(frozen=True)
class OrganizationScope:
    organization_id: str
    scope: str
    store_org_id: str | None


class OrganizationReportAccessError(PermissionError):
    pass


def resolve_organization_scope(
    organization_id: str,
    *,
    request_org_id: str | None = None,
) -> OrganizationScope:
    normalized_org_id = _normalize_string(organization_id)
    if not normalized_org_id:
        raise ValueError("organization_id must not be empty")
    normalized_org_id_key = normalized_org_id.lower()

    normalized_request_org_id = _normalize_optional_string(request_org_id)
    if normalized_request_org_id is not None:
        if normalized_org_id_key in UNSCOPED_ORGANIZATION_IDS:
            raise OrganizationReportAccessError(
                "Organization-scoped requests cannot access the unscoped organization report."
            )
        if normalized_org_id != normalized_request_org_id:
            raise OrganizationReportAccessError(
                "organization_id does not match the active X-Org-ID scope."
            )
        return OrganizationScope(
            organization_id=normalized_request_org_id,
            scope="organization",
            store_org_id=normalized_request_org_id,
        )

    if normalized_org_id_key in UNSCOPED_ORGANIZATION_IDS:
        return OrganizationScope(
            organization_id=normalized_org_id,
            scope="global",
            store_org_id=None,
        )

    return OrganizationScope(
        organization_id=normalized_org_id,
        scope="organization",
        store_org_id=normalized_org_id,
    )


class OrganizationReportService:
    def __init__(
        self,
        *,
        session_store: SessionStore,
        scenario_catalog: Mapping[str, Any],
        persona_catalog: Mapping[str, Any],
    ) -> None:
        self._session_store = session_store
        self._scenario_catalog = dict(scenario_catalog)
        self._persona_catalog = dict(persona_catalog)

    def build_report(
        self,
        organization_id: str,
        *,
        request_org_id: str | None = None,
    ) -> dict[str, Any]:
        scope = resolve_organization_scope(
            organization_id,
            request_org_id=request_org_id,
        )
        session_payloads = self._list_session_payloads(scope.store_org_id)
        sessions = [
            session_summary
            for payload in session_payloads
            if (session_summary := self._build_session_summary(payload)) is not None
        ]
        sessions.sort(
            key=lambda item: (
                _normalize_string(item.get("updated_at")),
                _normalize_string(item.get("session_id")),
            ),
            reverse=True,
        )

        learners: dict[str, list[dict[str, Any]]] = {}
        for session in sessions:
            learners.setdefault(session["learner_id"], []).append(session)

        learner_rows = [
            self._build_learner_summary(learner_id, learner_sessions)
            for learner_id, learner_sessions in learners.items()
        ]
        learner_rows.sort(
            key=lambda item: (
                0 if item["needs_attention"] else 1,
                -_severity_rank(item["highest_compliance_severity"]),
                item["average_score"] if item["average_score"] is not None else 10_000,
                -len(item["recent_reviews"]),
                _normalize_string(item["learner_id"]),
            )
        )

        finalized_scores = [
            float(session["overall_score"])
            for session in sessions
            if isinstance(session.get("overall_score"), int)
        ]
        team_recurring_weaknesses = self._aggregate_weaknesses(sessions)
        practice_completion_rate = (
            round(
                sum(1 for session in sessions if session["review_ready"]) / len(sessions),
                3,
            )
            if sessions
            else 0.0
        )

        latest_activity_at = next(
            (
                _normalize_optional_string(session.get("updated_at"))
                for session in sessions
                if _normalize_optional_string(session.get("updated_at")) is not None
            ),
            None,
        )
        team_summary = {
            "learner_count": len(learner_rows),
            "total_sessions": len(sessions),
            "finalized_sessions": sum(1 for session in sessions if session["review_ready"]),
            "active_sessions": sum(1 for session in sessions if not session["review_ready"]),
            "average_score": _average(finalized_scores) if finalized_scores else None,
            "practice_completion_rate": practice_completion_rate,
            "compliance_risk_session_count": sum(
                1
                for session in sessions
                if _severity_rank(session["max_compliance_severity"])
                >= COMPLIANCE_SEVERITY_RANK["medium"]
            ),
            "high_risk_session_count": sum(
                1
                for session in sessions
                if _severity_rank(session["max_compliance_severity"])
                >= COMPLIANCE_SEVERITY_RANK["high"]
            ),
            "at_risk_learner_count": sum(1 for learner in learner_rows if learner["needs_attention"]),
            "recurring_weaknesses": team_recurring_weaknesses,
            "latest_activity_at": latest_activity_at,
        }
        return {
            "organization_id": scope.organization_id,
            "organization_scope": scope.scope,
            "generated_at": _utc_now_iso(),
            "team_summary": team_summary,
            "learners": learner_rows,
        }

    def _list_session_payloads(self, org_id: str | None) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]]
        try:
            if org_id is None:
                payloads = self._session_store.list_all()
            else:
                payloads = self._session_store.list_all(org_id=org_id)
        except TypeError:
            payloads = self._session_store.list_all()

        filtered: list[dict[str, Any]] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            payload_org_id = _session_org_id(payload)
            if org_id is None:
                if payload_org_id is not None:
                    continue
            elif payload_org_id != org_id:
                continue
            filtered.append(payload)
        return filtered

    def _build_session_summary(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        learner_id = _normalize_string(payload.get("learner_id"))
        session_id = _normalize_string(payload.get("session_id"))
        scenario_id = _normalize_string(payload.get("scenario_id"))
        if not learner_id or not session_id or not scenario_id:
            return None

        review = _string_mapping(payload.get("review"))
        continuity_context = _string_mapping(payload.get("continuity_context"))
        prompt_summary = summarize_prompt_context(payload.get("prompt_context"))
        scenario = self._scenario_catalog.get(scenario_id)
        persona_id = _normalize_optional_string(
            _string_mapping(payload.get("context")).get("persona_id")
        )
        if scenario is not None:
            persona_id = _normalize_optional_string(getattr(scenario, "doctor_persona_id", None)) or persona_id
        persona = self._persona_catalog.get(persona_id) if persona_id is not None else None

        overall_score = _safe_int(review.get("overall_score"))
        priority_subskills = _priority_subskills(
            review,
            list(getattr(scenario, "focus_subskills", [])) if scenario is not None else [],
        )
        compliance_flags = review.get("compliance_flags")
        compliance_severities = [
            severity
            for severity in (
                _normalize_optional_string(_string_mapping(item).get("severity"))
                for item in (compliance_flags if isinstance(compliance_flags, list) else [])
            )
            if severity is not None
        ]
        prompt_profile = _normalize_optional_string(prompt_summary.get("profile_id"))
        return {
            "session_id": session_id,
            "learner_id": learner_id,
            "learner_hash": self._hash_identifier(learner_id),
            "scenario_id": scenario_id,
            "scenario_title": getattr(scenario, "title", None) or scenario_id,
            "persona_label": (
                _normalize_optional_string(persona.get("label"))
                if isinstance(persona, dict)
                else None
            ),
            "status": _normalize_string(payload.get("status")) or "unknown",
            "started_at": _normalize_string(payload.get("started_at")),
            "updated_at": _normalize_string(payload.get("updated_at")),
            "finish_reason": _normalize_optional_string(payload.get("finish_reason")),
            "overall_score": overall_score,
            "overall_band": _overall_band(review, overall_score),
            "prompt_profile": prompt_profile,
            "experiment_id": _normalize_optional_string(prompt_summary.get("experiment_id")),
            "max_compliance_severity": _max_compliance_severity(compliance_severities),
            "priority_subskills": priority_subskills,
            "active_focus_subskills": _active_focus_subskills(
                review,
                continuity_context,
                priority_subskills,
            ),
            "review_ready": _normalize_string(payload.get("status")) == "finalized" and bool(review),
        }

    def _build_learner_summary(
        self,
        learner_id: str,
        sessions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        finalized_sessions = [session for session in sessions if session["review_ready"]]
        active_sessions = [session for session in sessions if not session["review_ready"]]
        finalized_scores = [
            float(session["overall_score"])
            for session in finalized_sessions
            if isinstance(session.get("overall_score"), int)
        ]
        latest_session = sessions[0]
        latest_scored_session = next(
            (session for session in sessions if isinstance(session.get("overall_score"), int)),
            None,
        )

        weakness_rows = self._aggregate_weaknesses(sessions)
        completion_rate = (
            round(len(finalized_sessions) / len(sessions), 3)
            if sessions
            else 0.0
        )
        highest_compliance_severity = _max_compliance_severity(
            session["max_compliance_severity"]
            for session in sessions
            if session.get("max_compliance_severity") is not None
        )
        average_score = _average(finalized_scores) if finalized_scores else None
        last_score = (
            int(latest_scored_session["overall_score"])
            if latest_scored_session is not None and isinstance(latest_scored_session.get("overall_score"), int)
            else None
        )
        reasons = _needs_attention_reasons(
            average_score=average_score,
            last_score=last_score,
            completion_rate=completion_rate,
            highest_compliance_severity=highest_compliance_severity,
            recurring_weaknesses=weakness_rows,
        )
        return {
            "learner_id": learner_id,
            "learner_hash": latest_session["learner_hash"],
            "total_sessions": len(sessions),
            "finalized_sessions": len(finalized_sessions),
            "active_sessions": len(active_sessions),
            "average_score": average_score,
            "last_score": last_score,
            "practice_completion_rate": completion_rate,
            "highest_compliance_severity": highest_compliance_severity,
            "recurring_weaknesses": weakness_rows,
            "active_focus_subskills": _string_list(
                [session_skill for session in sessions[:2] for session_skill in session["active_focus_subskills"]],
                max_items=4,
            ),
            "needs_attention": len(reasons) > 0,
            "needs_attention_reasons": reasons,
            "latest_session_at": _normalize_optional_string(latest_session.get("updated_at")),
            "latest_scenario_title": _normalize_optional_string(latest_session.get("scenario_title")),
            "recent_reviews": [
                {
                    "session_id": session["session_id"],
                    "learner_id": session["learner_id"],
                    "scenario_id": session["scenario_id"],
                    "scenario_title": session["scenario_title"],
                    "persona_label": session["persona_label"],
                    "status": session["status"],
                    "started_at": session["started_at"],
                    "updated_at": session["updated_at"],
                    "finish_reason": session["finish_reason"],
                    "overall_score": session["overall_score"],
                    "overall_band": session["overall_band"],
                    "prompt_profile": session["prompt_profile"],
                    "max_compliance_severity": session["max_compliance_severity"],
                    "priority_subskills": list(session["priority_subskills"]),
                    "review_ready": bool(session["review_ready"]),
                }
                for session in finalized_sessions[:4]
            ],
        }

    def _aggregate_weaknesses(self, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        weakness_counts: dict[str, dict[str, Any]] = {}
        for session in sessions:
            learner_id = _normalize_string(session.get("learner_id"))
            for subskill_id in _string_list(session.get("priority_subskills"), max_items=4):
                payload = weakness_counts.setdefault(
                    subskill_id,
                    {
                        "subskill_id": subskill_id,
                        "occurrences": 0,
                        "affected_learner_ids": set(),
                    },
                )
                payload["occurrences"] += 1
                if learner_id:
                    payload["affected_learner_ids"].add(learner_id)

        rows = [
            {
                "subskill_id": subskill_id,
                "occurrences": int(payload["occurrences"]),
                "affected_learners": len(payload["affected_learner_ids"]),
            }
            for subskill_id, payload in weakness_counts.items()
        ]
        rows.sort(
            key=lambda item: (
                -int(item["occurrences"]),
                -int(item["affected_learners"]),
                _normalize_string(item["subskill_id"]),
            )
        )
        return rows[:6]

    def _hash_identifier(self, value: str) -> str | None:
        import hashlib

        normalized = _normalize_optional_string(value)
        if normalized is None:
            return None
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
