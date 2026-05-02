from __future__ import annotations

from typing import Any, Iterable

from scenarios.asset_loader import ScenarioRecord
from services.recommendation_engine import summarize_weakness_clusters


PERSISTENT_WEAK_AVERAGE_THRESHOLD = 2.6
PERSISTENT_WEAK_MIN_HISTORY = 3
TEACHING_PLAN_ACHIEVEMENT_STATUSES = {
    "achieved",
    "partially_achieved",
    "not_achieved",
    "not_observable",
    "no_plan",
}

_SUBSKILL_ACTIONS = {
    "opening": "Open with permission and one concise relevance statement before expanding.",
    "profiling": "Ask one targeted context question before moving into product detail.",
    "scientific_delivery": "Use one evidence-backed point and make the patient segment explicit.",
    "need_discovery": "Surface one concrete unmet need before shifting into persuasion.",
    "objection_handling": "Acknowledge the pushback first, then answer with specific support.",
    "closing_followup": "End with one realistic next step and an explicit follow-up path.",
}


def _unique_strings(items: Iterable[Any], *, max_items: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
        if max_items is not None and len(output) >= max_items:
            break
    return output


def _normalize_optional_string(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _normalize_teaching_plan(raw_plan: Any) -> dict[str, Any] | None:
    if not isinstance(raw_plan, dict):
        return None

    focus_subskills = _unique_strings(raw_plan.get("focus_subskills", []), max_items=3)
    reason = _normalize_optional_string(raw_plan.get("reason"))
    target_behavior = _normalize_optional_string(raw_plan.get("target_behavior"))
    success_criterion = _normalize_optional_string(raw_plan.get("success_criterion"))
    score_threshold = raw_plan.get("score_threshold", 4.0)
    version = raw_plan.get("version", 1)
    prior_evidence = _normalize_teaching_plan_prior_evidence(raw_plan.get("prior_evidence"))

    if not focus_subskills or reason is None or target_behavior is None or success_criterion is None:
        return None

    return {
        "version": int(version) if isinstance(version, (int, float)) else 1,
        "focus_subskills": focus_subskills,
        "reason": reason,
        "target_behavior": target_behavior,
        "success_criterion": success_criterion,
        "score_threshold": float(score_threshold) if isinstance(score_threshold, (int, float)) else 4.0,
        "prior_evidence": prior_evidence,
    }


def _normalize_teaching_plan_achievement(raw_achievement: Any) -> dict[str, Any] | None:
    if not isinstance(raw_achievement, dict):
        return None

    status = _normalize_optional_string(raw_achievement.get("status"))
    if status not in TEACHING_PLAN_ACHIEVEMENT_STATUSES:
        return None

    return {
        "status": status,
        "achieved_count": int(raw_achievement.get("achieved_count", 0))
        if isinstance(raw_achievement.get("achieved_count"), (int, float))
        else 0,
        "total_count": int(raw_achievement.get("total_count", 0))
        if isinstance(raw_achievement.get("total_count"), (int, float))
        else 0,
        "threshold": float(raw_achievement.get("threshold", 4.0))
        if isinstance(raw_achievement.get("threshold"), (int, float))
        else 4.0,
    }


def _normalize_teaching_plan_prior_evidence(raw_evidence: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_evidence, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, int | None]] = set()
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        summary = _normalize_optional_string(item.get("summary"))
        if summary is None:
            continue
        subskill_id = _normalize_optional_string(item.get("subskill_id"))
        turn_index = (
            int(item.get("turn_index"))
            if isinstance(item.get("turn_index"), (int, float)) and int(item.get("turn_index")) > 0
            else None
        )
        dedupe_key = (summary, subskill_id, turn_index)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "summary": summary,
                "subskill_id": subskill_id,
                "turn_index": turn_index,
                "session_id": _normalize_optional_string(item.get("session_id")),
                "scenario_id": _normalize_optional_string(item.get("scenario_id")),
                "scenario_title": _normalize_optional_string(item.get("scenario_title")),
            }
        )
        if len(normalized) >= 3:
            break
    return normalized


def _collect_teaching_plan_prior_evidence(
    *,
    review: dict[str, Any],
    focus_subskills: list[str],
    latest_session: dict[str, Any],
) -> list[dict[str, Any]]:
    subskills = review.get("subskills", {})
    if not isinstance(subskills, dict):
        return []

    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | None]] = set()
    for subskill_id in focus_subskills:
        payload = subskills.get(subskill_id, {})
        if not isinstance(payload, dict):
            continue
        evidence_items = payload.get("evidence", [])
        if not isinstance(evidence_items, list):
            continue
        for evidence in evidence_items:
            summary: str | None = None
            turn_index: int | None = None
            if isinstance(evidence, str):
                summary = _normalize_optional_string(evidence)
            elif isinstance(evidence, dict):
                summary = _normalize_optional_string(evidence.get("summary")) or _normalize_optional_string(
                    evidence.get("excerpt")
                )
                if isinstance(evidence.get("turn_index"), (int, float)) and int(evidence.get("turn_index")) > 0:
                    turn_index = int(evidence.get("turn_index"))
            if summary is None:
                continue
            dedupe_key = (subskill_id, summary, turn_index)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            collected.append(
                {
                    "summary": summary,
                    "subskill_id": subskill_id,
                    "turn_index": turn_index,
                    "session_id": _normalize_optional_string(latest_session.get("session_id")),
                    "scenario_id": _normalize_optional_string(latest_session.get("scenario_id")),
                    "scenario_title": _normalize_optional_string(latest_session.get("scenario_title")),
                }
            )
            break
        if len(collected) >= 3:
            break
    return collected


def default_action_for_subskill(subskill_id: str) -> str:
    return _SUBSKILL_ACTIONS.get(
        subskill_id,
        "Tighten the visit structure with a clearer objective and message flow.",
    )


def build_persona_summary(persona: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(persona.get("id", "")),
        "label": str(persona.get("label", "")).strip(),
        "specialty": str(persona.get("specialty", "")).strip(),
        "attitude": str(persona.get("attitude", "")).strip(),
        "time_pressure": str(persona.get("time_pressure", "")).strip(),
        "decision_style": str(persona.get("decision_style", "")).strip(),
        "more_receptive_when": _unique_strings(
            persona.get("becomes_more_receptive_when", []),
            max_items=2,
        ),
        "less_receptive_when": _unique_strings(
            persona.get("becomes_less_receptive_when", []),
            max_items=2,
        ),
    }


def build_scenario_summary(scenario: ScenarioRecord, persona: dict[str, Any]) -> dict[str, Any]:
    persona_summary = build_persona_summary(persona)
    return {
        "id": scenario.id,
        "title": scenario.title,
        "difficulty": scenario.difficulty,
        "focus_subskills": list(scenario.focus_subskills),
        "doctor_persona_id": scenario.doctor_persona_id,
        "persona_label": persona_summary["label"] or scenario.doctor_persona_id,
        "persona_attitude": persona_summary["attitude"],
        "persona_time_pressure": persona_summary["time_pressure"],
        "persona_specialty": persona_summary["specialty"],
        "max_turns": scenario.max_turns,
        "success_criteria": list(scenario.success_criteria),
        "failure_patterns": list(scenario.failure_patterns),
    }


def _collect_focus_subskills(review: dict[str, Any]) -> list[str]:
    coaching_feedback = review.get("coaching_feedback", {})
    if isinstance(coaching_feedback, dict):
        focus_subskills = _unique_strings(
            coaching_feedback.get("focus_subskills", []),
            max_items=3,
        )
        if focus_subskills:
            return focus_subskills

    return _unique_strings(review.get("priority_subskills", []), max_items=3)


def _collect_next_actions(review: dict[str, Any], carryover_focus_subskills: list[str]) -> list[str]:
    coaching_feedback = review.get("coaching_feedback", {})
    actions: list[str] = []
    if isinstance(coaching_feedback, dict):
        actions.extend(_unique_strings(coaching_feedback.get("next_actions", []), max_items=4))

    for subskill_id in carryover_focus_subskills:
        actions.append(default_action_for_subskill(subskill_id))

    return _unique_strings(actions, max_items=4)


def _collect_diagnosis_summaries(review: dict[str, Any]) -> list[str]:
    diagnosis = review.get("diagnosis", {})
    if not isinstance(diagnosis, dict):
        return []

    primary = diagnosis.get("primary", [])
    if not isinstance(primary, list):
        return []

    summaries: list[Any] = []
    for item in primary:
        if not isinstance(item, dict):
            continue
        summaries.append(item.get("summary"))
        if len(summaries) >= 3:
            break
    return _unique_strings(summaries, max_items=3)


def _collect_recent_personas(recent_history: list[dict[str, Any]]) -> list[str]:
    labels = [
        history_item.get("persona_label")
        for history_item in reversed(recent_history)
        if isinstance(history_item, dict)
    ]
    return _unique_strings(labels, max_items=3)


def _collect_recurring_weaknesses(recent_history: list[dict[str, Any]]) -> list[str]:
    clusters = summarize_weakness_clusters(recent_history, max_items=3)
    weaknesses: list[Any] = []
    for cluster in clusters:
        weaknesses.extend(cluster.subskills)
    return _unique_strings(weaknesses, max_items=4)


def _collect_persistent_weaknesses(subskill_signals: dict[str, dict[str, Any]]) -> list[str]:
    ranked: list[tuple[float, str]] = []
    for subskill_id, signal in subskill_signals.items():
        if not isinstance(subskill_id, str) or not isinstance(signal, dict):
            continue
        trend = str(signal.get("trend", "stable"))
        rolling_average = signal.get("rolling_average", 0.0)
        history_count = signal.get("history_count", 0)
        if not isinstance(rolling_average, (int, float)):
            continue
        if not isinstance(history_count, (int, float)):
            continue
        if trend != "declining" and (
            history_count < PERSISTENT_WEAK_MIN_HISTORY
            or float(rolling_average) > PERSISTENT_WEAK_AVERAGE_THRESHOLD
        ):
            continue
        ranked.append((float(rolling_average), subskill_id))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [subskill_id for _, subskill_id in ranked[:4]]


def build_coach_memory(
    *,
    review: dict[str, Any],
    recent_history: list[dict[str, Any]],
    subskill_signals: dict[str, dict[str, Any]],
    updated_at: str,
) -> dict[str, Any]:
    recurring_weaknesses = _collect_recurring_weaknesses(recent_history)
    persistent_weaknesses = _collect_persistent_weaknesses(subskill_signals)
    latest_focus_subskills = _collect_focus_subskills(review)
    carryover_focus_subskills = _unique_strings(
        [*latest_focus_subskills, *recurring_weaknesses, *persistent_weaknesses],
        max_items=3,
    )
    next_actions = _collect_next_actions(review, carryover_focus_subskills)
    diagnosis_summaries = _collect_diagnosis_summaries(review)
    recent_personas = _collect_recent_personas(recent_history)
    continuity_channel = review.get("continuity_channel", {})
    teaching_plan_achievement = _normalize_teaching_plan_achievement(
        continuity_channel.get("teaching_plan_achievement")
        if isinstance(continuity_channel, dict)
        else None
    )

    latest_session = recent_history[-1] if recent_history else {}
    if not isinstance(latest_session, dict):
        latest_session = {}

    # Build Teaching Plan
    plan_subskills = carryover_focus_subskills[:2] if carryover_focus_subskills else latest_focus_subskills[:1]
    plan_reason = "Recurring pattern in recent sessions." if recurring_weaknesses else "Area for improvement from last session."
    if teaching_plan_achievement is not None:
        achievement_status = teaching_plan_achievement["status"]
        if achievement_status == "achieved":
            plan_reason = "Previous teaching-plan target was achieved; shift to the next highest-impact gap."
        elif achievement_status == "partially_achieved":
            plan_reason = "Previous teaching-plan target was only partially achieved and needs one more focused pass."
        elif achievement_status == "not_achieved":
            plan_reason = "Previous teaching-plan target was not achieved and should stay active in the next run."
        elif achievement_status == "not_observable":
            plan_reason = "Previous teaching-plan target was not observable in the last session; pick a scenario that covers the target subskills."
    if persistent_weaknesses:
        plan_reason = "Persistent weakness requiring focused attention."

    prior_evidence = _collect_teaching_plan_prior_evidence(
        review=review,
        focus_subskills=plan_subskills,
        latest_session=latest_session,
    )

    teaching_plan = {
        "version": 1,
        "focus_subskills": plan_subskills,
        "reason": plan_reason,
        "target_behavior": next_actions[0] if next_actions else "Focus on core subskill delivery.",
        "success_criterion": f"Achieve a score of 4.0 or higher in {', '.join(plan_subskills)}",
        "score_threshold": 4.0,
        "prior_evidence": prior_evidence,
    }

    summary_parts: list[str] = []
    if carryover_focus_subskills:
        summary_parts.append(
            f"Carry over {', '.join(carryover_focus_subskills)} into the next practice run."
        )
    if teaching_plan_achievement is not None:
        achievement_status = teaching_plan_achievement["status"]
        if achievement_status == "achieved":
            summary_parts.append("The last frozen teaching-plan target was achieved.")
        elif achievement_status == "partially_achieved":
            summary_parts.append("The last frozen teaching-plan target was only partially achieved.")
        elif achievement_status == "not_achieved":
            summary_parts.append("The last frozen teaching-plan target still needs more work.")
        elif achievement_status == "not_observable":
            summary_parts.append("The last frozen teaching-plan target could not be observed in this session.")
    if recurring_weaknesses:
        summary_parts.append(f"Recurring weakness: {', '.join(recurring_weaknesses[:3])}.")
    overall_score = latest_session.get("overall_score")
    if isinstance(overall_score, (int, float)):
        summary_parts.append(f"Last session score: {int(overall_score)}/100.")

    return {
        "version": 1,
        "summary": " ".join(summary_parts).strip()
        or "No continuity signal has been established yet.",
        "active_focus_subskills": carryover_focus_subskills,
        "next_actions": next_actions,
        "teaching_plan": teaching_plan,
        "last_teaching_plan_achievement": teaching_plan_achievement,
        "recurring_weaknesses": recurring_weaknesses,
        "persistent_weaknesses": persistent_weaknesses,
        "recent_personas": recent_personas,
        "last_diagnosis_summaries": diagnosis_summaries,
        "last_session": {
            "session_id": str(latest_session.get("session_id", "")),
            "scenario_id": str(latest_session.get("scenario_id", "")),
            "scenario_title": str(latest_session.get("scenario_title", "")),
            "persona_label": str(latest_session.get("persona_label", "")),
            "overall_score": int(overall_score) if isinstance(overall_score, (int, float)) else None,
            "timestamp": str(latest_session.get("timestamp", updated_at)),
        },
        "updated_at": updated_at,
    }


def build_session_continuity(
    *,
    coach_memory: dict[str, Any] | None,
    scenario: ScenarioRecord,
    persona: dict[str, Any],
    session_id: str,
    started_at: str,
    active_training_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    persona_summary = build_persona_summary(persona)
    memory = coach_memory if isinstance(coach_memory, dict) else {}
    carryover_focus_subskills = _unique_strings(memory.get("active_focus_subskills", []), max_items=3)
    suggested_focus_subskills = _unique_strings(
        [*carryover_focus_subskills, *scenario.focus_subskills],
        max_items=4,
    )
    next_actions = _unique_strings(memory.get("next_actions", []), max_items=4)
    if not next_actions:
        next_actions = [
            default_action_for_subskill(subskill_id)
            for subskill_id in suggested_focus_subskills[:3]
        ]

    if carryover_focus_subskills:
        summary = (
            f"Carry over {', '.join(carryover_focus_subskills)} from recent sessions. "
            f"Against {persona_summary['label'] or scenario.doctor_persona_id}, "
            f"keep this visit tight around {', '.join(suggested_focus_subskills[:3])}."
        )
    else:
        summary = (
            f"Use this session as the baseline for {persona_summary['label'] or scenario.doctor_persona_id}. "
            f"Prioritize {', '.join(suggested_focus_subskills[:3])}."
        )

    # Freeze coach-derived teaching plan
    teaching_plan = _normalize_teaching_plan(memory.get("teaching_plan"))
    last_session = memory.get("last_session", {}) if isinstance(memory.get("last_session"), dict) else {}
    teaching_plan_snapshot = None
    if teaching_plan is not None:
        teaching_plan_snapshot = {
            "snapshot_id": f"tp_{session_id}",
            "plan_version": int(teaching_plan["version"]),
            "frozen_at": started_at,
            "source_updated_at": _normalize_optional_string(memory.get("updated_at")),
            "source_session_id": _normalize_optional_string(last_session.get("session_id")),
            "source_scenario_id": _normalize_optional_string(last_session.get("scenario_id")),
            "source_scenario_title": _normalize_optional_string(last_session.get("scenario_title")),
        }

    # Freeze active admin-created training plan
    training_plan_snapshot = None
    normalized_training_plan = None
    if isinstance(active_training_plan, dict):
        normalized_training_plan = {
            "plan_id": str(active_training_plan.get("plan_id", "")),
            "title": str(active_training_plan.get("title", "")),
            "target_subskills": _unique_strings(active_training_plan.get("target_subskills", [])),
            "required_scenario_ids": _unique_strings(active_training_plan.get("required_scenario_ids", [])),
            "goal_criteria": str(active_training_plan.get("goal_criteria", "")),
            "success_threshold": float(active_training_plan.get("success_threshold", 4.0)),
            "due_date": _normalize_optional_string(active_training_plan.get("due_date")),
        }
        training_plan_snapshot = {
            "snapshot_id": f"admin_plan_{session_id}",
            "plan_id": str(active_training_plan.get("plan_id", "")),
            "frozen_at": started_at,
            "title": str(active_training_plan.get("title", "")),
        }

    return {
        "version": 1,
        "summary": summary,
        "carryover_focus_subskills": carryover_focus_subskills,
        "scenario_focus_subskills": list(scenario.focus_subskills),
        "suggested_focus_subskills": suggested_focus_subskills,
        "next_actions": next_actions,
        "teaching_plan": teaching_plan,
        "teaching_plan_snapshot": teaching_plan_snapshot,
        "training_plan": normalized_training_plan,
        "training_plan_snapshot": training_plan_snapshot,
        "recent_personas": _unique_strings(memory.get("recent_personas", []), max_items=3),
        "last_diagnosis_summaries": _unique_strings(
            memory.get("last_diagnosis_summaries", []),
            max_items=3,
        ),
        "persona": persona_summary,
        "success_criteria": list(scenario.success_criteria),
        "failure_patterns": list(scenario.failure_patterns),
    }
