from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable

from scenarios.asset_loader import CurriculumRecord, ScenarioRecord
from services.curriculum_service import CurriculumProgressState


DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
DIFFICULTY_LABELS = {value: key for key, value in DIFFICULTY_ORDER.items()}
HIGH_RISK_SEVERITIES = {"high", "critical"}
PERSISTENT_WEAK_AVERAGE_THRESHOLD = 2.6
PERSISTENT_WEAK_MIN_HISTORY = 3
RECENT_SCENARIO_PENALTY_WINDOW = 5
TEACHING_PLAN_ACHIEVEMENT_STATUSES = {
    "achieved",
    "partially_achieved",
    "not_achieved",
    "not_observable",
    "no_plan",
}


@dataclass(frozen=True)
class ScenarioRecommendation:
    scenario_id: str
    title: str
    difficulty: str
    target_subskills: list[str]
    reason: str
    recommendation_type: str = "skill"  # "skill", "compliance", "mixed", "continuity"
    evidence_source: str | None = None
    stop_condition: str | None = None
    expected_difficulty: str | None = None
    suggested_repetition_count: int = 1
    reason_category: str = "skill"
    urgency: str = "routine"  # "immediate", "soon", "routine"
    urgency_reason: str | None = None


@dataclass(frozen=True)
class WeaknessCluster:
    cluster_id: str
    subskills: list[str]
    occurrences: int
    last_seen_at: str


def _unique_strings(items: Iterable[Any]) -> list[str]:
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
    return output


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _normalize_teaching_plan_achievement(raw_achievement: Any) -> dict[str, Any] | None:
    if not isinstance(raw_achievement, dict):
        return None

    status = raw_achievement.get("status")
    if not isinstance(status, str):
        return None
    normalized_status = status.strip()
    if normalized_status not in TEACHING_PLAN_ACHIEVEMENT_STATUSES:
        return None

    return {
        "status": normalized_status,
        "achieved_count": _safe_int(raw_achievement.get("achieved_count"), default=0),
        "total_count": _safe_int(raw_achievement.get("total_count"), default=0),
        "threshold": _safe_float(raw_achievement.get("threshold"), default=4.0),
    }


def _latest_teaching_plan_achievement(
    *,
    review: dict[str, Any],
    recent_history: list[dict[str, Any]],
) -> dict[str, Any] | None:
    continuity_channel = review.get("continuity_channel", {})
    if isinstance(continuity_channel, dict):
        normalized = _normalize_teaching_plan_achievement(
            continuity_channel.get("teaching_plan_achievement")
        )
        if normalized is not None:
            return normalized

    for history_item in reversed(recent_history):
        if not isinstance(history_item, dict):
            continue
        normalized = _normalize_teaching_plan_achievement(
            history_item.get("teaching_plan_achievement")
        )
        if normalized is not None:
            return normalized
    return None


def _teaching_plan_focus_subskills(
    *,
    frozen_teaching_plan: dict[str, Any] | None,
    carryover_subskills: list[str],
) -> list[str]:
    if isinstance(frozen_teaching_plan, dict):
        focus_subskills = _unique_strings(frozen_teaching_plan.get("focus_subskills", []))
        if focus_subskills:
            return focus_subskills[:3]
    return _unique_strings(carryover_subskills)[:3]


def _collect_low_score_subskills(review: dict[str, Any]) -> list[str]:
    review_subskills = review.get("subskills", {})
    if not isinstance(review_subskills, dict):
        return []

    ranked: list[tuple[float, str]] = []
    for subskill_id, payload in review_subskills.items():
        if not isinstance(subskill_id, str) or not isinstance(payload, dict):
            continue
        score = _safe_float(payload.get("score"), default=5.0)
        if score > 2.0:
            continue
        ranked.append((score, subskill_id))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [subskill_id for _, subskill_id in ranked]


def derive_session_weak_subskills(
    review: dict[str, Any],
    fallback_subskills: list[str],
    *,
    max_items: int = 4,
) -> list[str]:
    collected: list[Any] = []

    priority_subskills = review.get("priority_subskills", [])
    if isinstance(priority_subskills, list):
        collected.extend(priority_subskills)

    diagnosis = review.get("diagnosis", {})
    if isinstance(diagnosis, dict):
        primary = diagnosis.get("primary", [])
        if isinstance(primary, list):
            for entry in primary:
                if not isinstance(entry, dict):
                    continue
                collected.extend(entry.get("recommendation_focus", []))
                collected.extend(entry.get("related_subskills", []))

    collected.extend(_collect_low_score_subskills(review))
    collected.extend(fallback_subskills)
    return _unique_strings(collected)[:max_items]


def _difficulty_distance(left: str, right: str) -> int:
    return abs(DIFFICULTY_ORDER.get(left, 1) - DIFFICULTY_ORDER.get(right, 1))


def _desired_difficulty(
    *,
    overall_score: int,
    current_scenario_difficulty: str,
    has_high_risk: bool,
) -> str:
    current_level = DIFFICULTY_ORDER.get(current_scenario_difficulty, 1)

    if has_high_risk or overall_score < 45:
        target_level = max(0, current_level - 1)
    elif overall_score >= 85:
        target_level = min(2, current_level + 1)
    elif overall_score >= 70:
        target_level = current_level
    else:
        target_level = min(1, current_level)

    return DIFFICULTY_LABELS[target_level]


def _diagnosis_label(review: dict[str, Any]) -> str | None:
    diagnosis = review.get("diagnosis", {})
    if not isinstance(diagnosis, dict):
        return None

    primary = diagnosis.get("primary", [])
    if not isinstance(primary, list) or not primary:
        return None

    first = primary[0]
    if not isinstance(first, dict):
        return None

    summary = first.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip().rstrip(".")

    diagnosis_id = first.get("id")
    if not isinstance(diagnosis_id, str) or not diagnosis_id.strip():
        return None
    return diagnosis_id.replace("_", " ")


def _collect_declining_subskills(subskill_signals: dict[str, dict[str, Any]]) -> list[str]:
    ranked: list[tuple[float, str]] = []
    for subskill_id, payload in subskill_signals.items():
        if not isinstance(subskill_id, str) or not isinstance(payload, dict):
            continue
        if str(payload.get("trend", "stable")) != "declining":
            continue
        ranked.append((_safe_float(payload.get("rolling_average"), default=5.0), subskill_id))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [subskill_id for _, subskill_id in ranked]


def _collect_persistently_weak_subskills(subskill_signals: dict[str, dict[str, Any]]) -> list[str]:
    ranked: list[tuple[float, str]] = []
    for subskill_id, payload in subskill_signals.items():
        if not isinstance(subskill_id, str) or not isinstance(payload, dict):
            continue
        history_count = _safe_int(payload.get("history_count"), default=0)
        rolling_average = _safe_float(payload.get("rolling_average"), default=5.0)
        if history_count < PERSISTENT_WEAK_MIN_HISTORY:
            continue
        if rolling_average > PERSISTENT_WEAK_AVERAGE_THRESHOLD:
            continue
        ranked.append((rolling_average, subskill_id))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [subskill_id for _, subskill_id in ranked]


def _collect_subskills_by_review_status(
    subskill_signals: dict[str, dict[str, Any]],
    *,
    review_statuses: set[str],
) -> list[str]:
    ranked: list[tuple[int, float, str]] = []
    for subskill_id, payload in subskill_signals.items():
        if not isinstance(subskill_id, str) or not isinstance(payload, dict):
            continue
        review_status = str(payload.get("review_status", "")).strip()
        if review_status not in review_statuses:
            continue
        next_review_in_sessions = _safe_int(payload.get("next_review_in_sessions"), default=0)
        rolling_average = _safe_float(payload.get("rolling_average"), default=0.0)
        ranked.append((next_review_in_sessions, -rolling_average, subskill_id))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [subskill_id for _, _, subskill_id in ranked]


def _collect_subskills_by_mastery_status(
    subskill_signals: dict[str, dict[str, Any]],
    *,
    mastery_statuses: set[str],
) -> list[str]:
    ranked: list[tuple[float, str]] = []
    for subskill_id, payload in subskill_signals.items():
        if not isinstance(subskill_id, str) or not isinstance(payload, dict):
            continue
        mastery_status = str(payload.get("mastery_status", "")).strip()
        if mastery_status not in mastery_statuses:
            continue
        ranked.append((_safe_float(payload.get("rolling_average"), default=0.0), subskill_id))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [subskill_id for _, subskill_id in ranked]


def _collect_recent_scenario_ids(recent_history: list[dict[str, Any]]) -> list[str]:
    recent_ids: list[str] = []
    for history_item in recent_history[-RECENT_SCENARIO_PENALTY_WINDOW:]:
        if not isinstance(history_item, dict):
            continue
        scenario_id = history_item.get("scenario_id")
        if not isinstance(scenario_id, str):
            continue
        normalized = scenario_id.strip()
        if normalized:
            recent_ids.append(normalized)
    return recent_ids


def _recent_medium_compliance_risk(recent_history: list[dict[str, Any]], *, max_window: int = 5) -> bool:
    medium_count = 0
    for history_item in recent_history[-max_window:]:
        if not isinstance(history_item, dict):
            continue
        severity = str(history_item.get("max_compliance_severity", "")).strip().lower()
        if severity == "medium":
            medium_count += 1
    return medium_count >= 2


def _reason_category(*, driver_flags: set[str]) -> str:
    if len(driver_flags) > 1:
        return "mixed"
    for category in ("compliance", "continuity", "curriculum", "skill"):
        if category in driver_flags:
            return category
    return "skill"


def _suggested_repetition_count(
    *,
    reason_category: str,
    dominant_cluster: WeaknessCluster | None,
    persistent_overlap: list[str],
    repeated_medium_risk: bool,
) -> int:
    if reason_category in {"compliance", "continuity", "mixed"}:
        return 2
    if repeated_medium_risk:
        return 2
    if persistent_overlap:
        return 2
    if dominant_cluster is not None and dominant_cluster.occurrences >= 3:
        return 2
    return 1


def _stop_condition(
    *,
    reason_category: str,
    primary_target_subskill: str | None,
    has_compliance_driver: bool,
    has_continuity_driver: bool,
    has_curriculum_driver: bool,
    extends_after_achieved_teaching_plan: bool = False,
) -> str:
    if has_compliance_driver and has_continuity_driver:
        if primary_target_subskill:
            return (
                f"Stop when {primary_target_subskill} reaches 4.0+, the next review shows compliant "
                "handling, and the frozen teaching-plan target is marked achieved."
            )
        return (
            "Stop when the next review shows compliant handling and the frozen teaching-plan "
            "target is marked achieved."
        )
    if reason_category == "compliance" or has_compliance_driver:
        return "Stop when the next review shows compliant handling with no high-risk compliance flag."
    if extends_after_achieved_teaching_plan:
        if primary_target_subskill:
            return (
                f"Stop when {primary_target_subskill} reaches 4.0+ and the learner can hold the harder step "
                "without reopening the previous target."
            )
        return "Stop when the learner can hold the harder step without reopening the previous target."
    if reason_category == "continuity" or has_continuity_driver:
        if primary_target_subskill:
            return (
                f"Stop when {primary_target_subskill} reaches 4.0+ and the frozen teaching-plan target is marked achieved."
            )
        return "Stop when the frozen teaching-plan target is marked achieved."
    if reason_category == "curriculum" or has_curriculum_driver:
        if primary_target_subskill:
            return (
                f"Stop when {primary_target_subskill} reaches 4.0+ and the learner can hold the harder step "
                "without reopening the previous target."
            )
        return "Stop when the learner can hold the harder step without reopening the previous target."
    if reason_category == "mixed":
        if primary_target_subskill:
            return (
                f"Stop when {primary_target_subskill} reaches 4.0+ and the next finalized review shows the target behavior is stable."
            )
        return "Stop when the next finalized review shows the target behavior is stable."
    if primary_target_subskill:
        return f"Stop when {primary_target_subskill} reaches 4.0+ in the next finalized review."
    return "Stop when the next finalized review shows the target behavior is stable."


def _compute_urgency(
    *,
    has_high_risk: bool,
    overall_score: int,
    declining_overlap: list[str],
    persistent_overlap: list[str],
    review_due_overlap: list[str],
    teaching_plan_status: str,
    has_compliance_driver: bool,
) -> tuple[str, str | None]:
    if has_high_risk or has_compliance_driver:
        return ("immediate", "Compliance risk requires urgent remedial practice.")
    if overall_score < 40:
        return ("immediate", "Critical skill gap requires immediate focused training.")
    if teaching_plan_status == "not_achieved":
        return ("soon", "Frozen teaching-plan target was not achieved; practice soon to close the gap.")
    if teaching_plan_status == "not_observable":
        return ("soon", "Teaching-plan target was not observable; re-target soon with a matching scenario.")
    if declining_overlap:
        return ("soon", f"Declining trend in {', '.join(declining_overlap[:2])} needs timely practice.")
    if persistent_overlap:
        return ("soon", f"Persistent weakness in {', '.join(persistent_overlap[:2])} needs sustained practice.")
    if review_due_overlap:
        return ("soon", "Spaced-review window is now due to prevent skill drift.")
    if teaching_plan_status == "partially_achieved":
        return ("routine", "Teaching-plan target was partially achieved; keep progressing.")
    return ("routine", "Practice at your regular pace to maintain and extend current skills.")


def summarize_weakness_clusters(
    recent_history: list[dict[str, Any]],
    *,
    max_window: int = 8,
    max_items: int = 3,
) -> list[WeaknessCluster]:
    if not recent_history or max_items <= 0:
        return []

    cluster_index: dict[tuple[str, ...], dict[str, Any]] = {}
    window = [item for item in recent_history[-max_window:] if isinstance(item, dict)]
    for position, history_item in enumerate(window):
        weak_subskills = sorted(_unique_strings(history_item.get("weak_subskills", []))[:4])
        if len(weak_subskills) < 2:
            continue

        last_seen_at = str(history_item.get("timestamp", "")).strip()
        max_cluster_size = min(3, len(weak_subskills))
        for cluster_size in range(max_cluster_size, 1, -1):
            for cluster_items in combinations(weak_subskills, cluster_size):
                state = cluster_index.setdefault(
                    cluster_items,
                    {
                        "subskills": list(cluster_items),
                        "occurrences": 0,
                        "last_seen_at": "",
                        "last_position": -1,
                    },
                )
                state["occurrences"] += 1
                state["last_seen_at"] = last_seen_at
                state["last_position"] = position

    ranked = sorted(
        cluster_index.values(),
        key=lambda item: (
            -int(item["occurrences"]),
            -len(item["subskills"]),
            -int(item["last_position"]),
            ",".join(item["subskills"]),
        ),
    )
    return [
        WeaknessCluster(
            cluster_id="+".join(item["subskills"]),
            subskills=list(item["subskills"]),
            occurrences=int(item["occurrences"]),
            last_seen_at=str(item["last_seen_at"]),
        )
        for item in ranked[:max_items]
    ]


def _build_reason(
    *,
    overlap: list[str],
    desired_difficulty: str,
    scenario: ScenarioRecord,
    current_scenario_difficulty: str,
    diagnosis_label: str | None,
    has_high_risk: bool,
    dominant_cluster: WeaknessCluster | None,
    declining_overlap: list[str],
    persistent_overlap: list[str],
    review_due_overlap: list[str],
    review_soon_overlap: list[str],
    teaching_plan_status: str,
    teaching_plan_overlap: list[str],
    curriculum_stage_title: str | None = None,
    curriculum_overlap: list[str] | None = None,
    fills_missing_curriculum_scenario: bool = False,
    repeats_curriculum_scenario: bool = False,
    parts_meta: dict[str, Any] | None = None,
) -> str:
    parts_meta = parts_meta or {}
    parts: list[str] = []
    curriculum_overlap = curriculum_overlap or []

    if overlap:
        parts.append(f"Targets {', '.join(overlap[:2])}.")
    else:
        parts.append("Covers the current weak-skill cluster from a broader angle.")

    failed_carryover_overlap = [skill for skill in overlap if skill in parts_meta.get("failed_carryover", [])]
    if failed_carryover_overlap:
        parts.append(f"Provides a remedial path for {', '.join(failed_carryover_overlap)} (carryover weakness).")
    elif teaching_plan_status == "not_achieved" and teaching_plan_overlap:
        parts.append(
            "Keeps the frozen teaching-plan target active because it was not achieved."
        )
    elif teaching_plan_status == "not_observable" and teaching_plan_overlap:
        parts.append(
            "Re-targets the frozen teaching-plan focus because it was not observable in the last session."
        )
    elif teaching_plan_status == "partially_achieved" and teaching_plan_overlap:
        parts.append(
            "Keeps the frozen teaching-plan target active after only partial achievement."
        )
    elif teaching_plan_status == "achieved" and not teaching_plan_overlap:
        parts.append("Moves on after the last frozen teaching-plan target was achieved.")

    if curriculum_stage_title:
        parts.append(f"Fits the current curriculum stage: {curriculum_stage_title}.")
        if fills_missing_curriculum_scenario:
            parts.append("Covers a required stage scenario that is still missing from recent practice.")
        elif repeats_curriculum_scenario:
            parts.append("Keeps the current stage active with another recommended repetition.")
        elif curriculum_overlap:
            parts.append(
                "Advances the current stage targets on "
                f"{', '.join(curriculum_overlap[:2])}."
            )

    if dominant_cluster is not None:
        cluster_overlap = [skill for skill in dominant_cluster.subskills if skill in scenario.focus_subskills]
        if len(cluster_overlap) == len(dominant_cluster.subskills):
            parts.append(
                "Reinforces the recurring "
                f"{', '.join(dominant_cluster.subskills)} pattern from recent sessions."
            )
        elif cluster_overlap:
            parts.append(
                "Keeps working on the recurring "
                f"{', '.join(dominant_cluster.subskills)} pattern."
            )

    if declining_overlap:
        parts.append(f"Addresses the longer-window decline in {', '.join(declining_overlap[:2])}.")
    elif persistent_overlap:
        parts.append(f"Supports persistently weak areas: {', '.join(persistent_overlap[:2])}.")

    if review_due_overlap:
        parts.append(
            f"Schedules a retention check for {', '.join(review_due_overlap[:2])} before the skill drifts."
        )
    elif review_soon_overlap and not declining_overlap and not persistent_overlap:
        parts.append(
            f"Keeps {', '.join(review_soon_overlap[:2])} warm ahead of the next review window."
        )

    if diagnosis_label:
        parts.append(f"Aligned with the latest diagnosis: {diagnosis_label}.")

    if scenario.difficulty == desired_difficulty:
        parts.append(f"Keeps the next run at {desired_difficulty} difficulty.")
    elif has_high_risk and _difficulty_distance(scenario.difficulty, current_scenario_difficulty) > 0:
        if DIFFICULTY_ORDER.get(scenario.difficulty, 1) < DIFFICULTY_ORDER.get(
            current_scenario_difficulty,
            1,
        ):
            parts.append("Steps difficulty down after the latest compliance risk.")
    elif DIFFICULTY_ORDER.get(scenario.difficulty, 1) > DIFFICULTY_ORDER.get(
        current_scenario_difficulty,
        1,
    ):
        parts.append("Raises difficulty to extend the current momentum.")

    return " ".join(parts)


def build_scenario_recommendations(
    *,
    scenarios: dict[str, ScenarioRecord],
    current_scenario_id: str,
    current_scenario_difficulty: str,
    review: dict[str, Any],
    recent_history: list[dict[str, Any]],
    subskill_trends: dict[str, str],
    fallback_subskills: list[str],
    frozen_teaching_plan: dict[str, Any] | None = None,
    frozen_training_plan: dict[str, Any] | None = None,
    subskill_signals: dict[str, dict[str, Any]] | None = None,
    curriculum: CurriculumRecord | None = None,
    curriculum_progress: CurriculumProgressState | None = None,
    max_items: int = 3,
) -> list[ScenarioRecommendation]:
    if not scenarios or max_items <= 0:
        return []

    continuity_channel = review.get("continuity_channel", {})
    carryover_subskills = continuity_channel.get("carryover_subskills", [])
    failed_carryover = [
        s for s in carryover_subskills
        if int(review.get("subskills", {}).get(s, {}).get("score", 5)) <= 2
    ]
    teaching_plan_achievement = _latest_teaching_plan_achievement(
        review=review,
        recent_history=recent_history,
    )
    teaching_plan_status = (
        str(teaching_plan_achievement.get("status", "no_plan"))
        if teaching_plan_achievement is not None
        else "no_plan"
    )
    teaching_plan_focus_subskills = _teaching_plan_focus_subskills(
        frozen_teaching_plan=frozen_teaching_plan,
        carryover_subskills=_unique_strings(carryover_subskills),
    )
    unresolved_teaching_plan = teaching_plan_status in {"not_achieved", "partially_achieved"}
    achieved_teaching_plan = teaching_plan_status == "achieved"

    # Extract training plan achievement from continuity channel
    training_plan_achievement = _normalize_teaching_plan_achievement(
        continuity_channel.get("training_plan_achievement")
        if isinstance(continuity_channel, dict)
        else None
    )
    training_plan_status = (
        str(training_plan_achievement.get("status", "no_plan"))
        if training_plan_achievement is not None
        else "no_plan"
    )
    training_plan_id = (
        str(continuity_channel.get("training_plan_id", ""))
        if isinstance(continuity_channel, dict)
        else ""
    )
    training_plan_target_subskills: list[str] = []
    if isinstance(frozen_training_plan, dict):
        training_plan_target_subskills = _unique_strings(frozen_training_plan.get("target_subskills", []))

    overall_score = int(review.get("overall_score", 0))
    compliance_flags = review.get("compliance_flags", [])
    has_high_risk = False
    has_medium_risk = False
    if isinstance(compliance_flags, list):
        has_high_risk = any(
            isinstance(flag, dict)
            and str(flag.get("severity", "")).lower() in HIGH_RISK_SEVERITIES
            for flag in compliance_flags
        )
        has_medium_risk = any(
            isinstance(flag, dict)
            and str(flag.get("severity", "")).lower() == "medium"
            for flag in compliance_flags
        )
    repeated_medium_risk = has_medium_risk and _recent_medium_compliance_risk(recent_history)
    risk_requires_remedial = has_high_risk or repeated_medium_risk

    subskill_signals = subskill_signals or {}
    declining_subskills = _collect_declining_subskills(subskill_signals)
    persistently_weak_subskills = _collect_persistently_weak_subskills(subskill_signals)
    review_due_subskills = _collect_subskills_by_review_status(
        subskill_signals,
        review_statuses={"due"},
    )
    review_soon_subskills = _collect_subskills_by_review_status(
        subskill_signals,
        review_statuses={"soon"},
    )
    mastered_subskills = _collect_subskills_by_mastery_status(
        subskill_signals,
        mastery_statuses={"mastered"},
    )
    target_subskills = _unique_strings(
        [
            *derive_session_weak_subskills(review, fallback_subskills),
            *declining_subskills,
            *persistently_weak_subskills,
        ]
    )[:4]
    target_subskill_set = set(target_subskills)
    desired_difficulty = _desired_difficulty(
        overall_score=overall_score,
        current_scenario_difficulty=current_scenario_difficulty,
        has_high_risk=risk_requires_remedial,
    )
    diagnosis_label = _diagnosis_label(review)
    weakness_clusters = summarize_weakness_clusters(recent_history)
    dominant_cluster = weakness_clusters[0] if weakness_clusters else None
    recent_ids = _collect_recent_scenario_ids(recent_history)
    current_curriculum_stage_id = (
        curriculum_progress.current_stage_id if curriculum_progress is not None else None
    )
    current_curriculum_stage_title = (
        curriculum_progress.current_stage_title if curriculum_progress is not None else None
    )
    current_curriculum_stage_scenarios = {
        item.scenario_id: item
        for item in (curriculum_progress.current_stage_scenarios if curriculum_progress is not None else [])
    }
    current_curriculum_target_subskills = set(
        curriculum_progress.target_subskills if curriculum_progress is not None else []
    )
    current_curriculum_stage_index = (
        curriculum.stage_index_by_id.get(current_curriculum_stage_id, -1)
        if curriculum is not None and current_curriculum_stage_id is not None
        else -1
    )

    # Build a map of scenario occurrence counts and achievement status from full recent history
    history_counts: dict[str, tuple[int, bool]] = {}
    for item in recent_history:
        sid = item.get("scenario_id")
        if not isinstance(sid, str):
            continue
        cnt, achieved = history_counts.get(sid, (0, False))
        cnt += 1
        scenario_record = scenarios.get(sid)
        achieved_now = False
        focus_subskill_scores = item.get("focus_subskill_scores", {})
        if isinstance(focus_subskill_scores, dict):
            focus_skills = (
                list(scenario_record.focus_subskills)
                if scenario_record is not None
                else [key for key in focus_subskill_scores.keys() if isinstance(key, str)]
            )
            relevant_scores = [
                _safe_float(focus_subskill_scores.get(skill), default=0.0)
                for skill in focus_skills
                if skill in focus_subskill_scores
            ]
            if relevant_scores:
                achieved_now = _average(relevant_scores) >= 4.0 and min(relevant_scores) >= 3.5
        if not achieved_now:
            focus_average = _safe_float(item.get("focus_subskill_average"), default=0.0)
            if focus_average > 0:
                achieved_now = focus_average >= 4.0
        if achieved_now:
            max_severity = str(item.get("max_compliance_severity", "")).strip().lower()
            if max_severity in HIGH_RISK_SEVERITIES:
                achieved_now = False
        if not achieved_now:
            weak = item.get("weak_subskills")
            achieved_now = not weak or (isinstance(weak, list) and len(weak) == 0)
        achieved = achieved or achieved_now
        history_counts[sid] = (cnt, achieved)

    ranked: list[tuple[int, int, str, ScenarioRecommendation]] = []
    for scenario in scenarios.values():
        if scenario.id == current_scenario_id:
            continue

        scenario_stage_id = (
            curriculum.scenario_to_stage_id.get(scenario.id)
            if curriculum is not None
            else None
        )
        repetition_cap = 2
        if scenario_stage_id is not None and curriculum is not None:
            stage = curriculum.stages.get(scenario_stage_id)
            if stage is not None:
                repetition_cap = max(1, stage.recommended_repetition)

        # Skip scenarios that have already been repeated enough times and were previously achieved.
        cnt_achieved = history_counts.get(scenario.id, (0, False))
        if cnt_achieved[0] >= repetition_cap and cnt_achieved[1]:
            continue

        overlap = [skill for skill in scenario.focus_subskills if skill in target_subskill_set]
        focus_set = set(scenario.focus_subskills)
        teaching_plan_overlap = [
            skill for skill in teaching_plan_focus_subskills if skill in focus_set
        ]
        review_due_overlap = [skill for skill in scenario.focus_subskills if skill in review_due_subskills]
        review_soon_overlap = [
            skill for skill in scenario.focus_subskills if skill in review_soon_subskills
        ]
        mastered_overlap = [skill for skill in scenario.focus_subskills if skill in mastered_subskills]
        difficulty_distance = _difficulty_distance(scenario.difficulty, desired_difficulty)

        score = len(overlap) * 12
        score += {0: 6, 1: 3}.get(difficulty_distance, 0)

        if any(subskill_trends.get(skill) == "declining" for skill in overlap):
            score += 4

        if review_due_overlap:
            score += 6 + (2 * len(review_due_overlap))
        elif review_soon_overlap:
            score += 3

        for skill in overlap:
            signal = subskill_signals.get(skill, {})
            if str(signal.get("trend", "stable")) == "declining":
                score += 3
            if (
                _safe_int(signal.get("history_count"), default=0) >= PERSISTENT_WEAK_MIN_HISTORY
                and _safe_float(signal.get("rolling_average"), default=5.0)
                <= PERSISTENT_WEAK_AVERAGE_THRESHOLD
            ):
                score += 2

        if dominant_cluster is not None and dominant_cluster.occurrences >= 2:
            cluster_overlap = [skill for skill in dominant_cluster.subskills if skill in focus_set]
            if len(cluster_overlap) == len(dominant_cluster.subskills):
                score += 8 + dominant_cluster.occurrences * 2
            elif cluster_overlap:
                score += 3 * len(cluster_overlap)

        for cluster in weakness_clusters[1:3]:
            cluster_overlap = [skill for skill in cluster.subskills if skill in focus_set]
            if len(cluster_overlap) == len(cluster.subskills):
                score += 2 + cluster.occurrences

        if scenario.id in recent_ids:
            score -= 4 if recent_ids and scenario.id == recent_ids[-1] else 2

        if risk_requires_remedial and scenario.difficulty == "hard":
            score -= 5

        training_plan_overlap = [
            skill for skill in training_plan_target_subskills if skill in focus_set
        ]
        if training_plan_overlap:
            if training_plan_status == "not_achieved":
                score += 10
            elif training_plan_status == "partially_achieved":
                score += 6
            elif training_plan_status == "achieved":
                score += 2  # Still slightly positive to maintain coverage
            elif training_plan_status == "no_plan":
                score += 8  # Newly active plan, no prior result yet

        if teaching_plan_overlap:
            if teaching_plan_status == "not_achieved":
                score += 11
            elif teaching_plan_status == "not_observable":
                score += 10
            elif teaching_plan_status == "partially_achieved":
                score += 7
            elif teaching_plan_status == "achieved" and not risk_requires_remedial:
                score -= 5
        elif achieved_teaching_plan and not risk_requires_remedial:
            score += 2
            if DIFFICULTY_ORDER.get(scenario.difficulty, 1) >= DIFFICULTY_ORDER.get(
                current_scenario_difficulty,
                1,
            ):
                score += 1

        overlap_failed: list[str] = []
        if failed_carryover:
            overlap_failed = [s for s in failed_carryover if s in focus_set]
            if overlap_failed:
                score += 15
                recommendation_type = "continuity"
            else:
                recommendation_type = "skill"
        elif unresolved_teaching_plan and teaching_plan_overlap:
            score += 8 if teaching_plan_status == "not_achieved" else 4
            recommendation_type = "continuity"
        else:
            recommendation_type = "compliance" if risk_requires_remedial and overlap else "skill"

        if not overlap:
            score -= 2

        declining_overlap = [skill for skill in overlap if skill in declining_subskills]
        persistent_overlap = [skill for skill in overlap if skill in persistently_weak_subskills]
        curriculum_overlap = [
            skill for skill in scenario.focus_subskills if skill in current_curriculum_target_subskills
        ]
        curriculum_stage_scenario = current_curriculum_stage_scenarios.get(scenario.id)
        fills_missing_curriculum_scenario = (
            curriculum_stage_scenario is not None
            and curriculum_stage_scenario.required
            and curriculum_stage_scenario.attempt_count == 0
        )
        repeats_curriculum_scenario = (
            curriculum_stage_scenario is not None
            and curriculum_stage_scenario.remaining_repetitions > 0
            and not fills_missing_curriculum_scenario
        )
        is_curriculum_stage_scenario = curriculum_stage_scenario is not None
        if (
            mastered_overlap
            and not review_due_overlap
            and not review_soon_overlap
            and not is_curriculum_stage_scenario
            and not overlap_failed
            and not risk_requires_remedial
        ):
            score -= 6 + (2 * len(mastered_overlap))
        if is_curriculum_stage_scenario:
            score += 8
        if fills_missing_curriculum_scenario:
            score += 10
        elif repeats_curriculum_scenario:
            score += 5
        elif curriculum_overlap:
            score += 4

        if curriculum is not None and current_curriculum_stage_index >= 0:
            scenario_stage_id = curriculum.scenario_to_stage_id.get(scenario.id)
            if scenario_stage_id is not None:
                scenario_stage_index = curriculum.stage_index_by_id.get(scenario_stage_id, -1)
                if scenario_stage_index > current_curriculum_stage_index:
                    score -= (
                        (7 if risk_requires_remedial else 3)
                        * (scenario_stage_index - current_curriculum_stage_index)
                    )
                elif (
                    scenario_stage_index < current_curriculum_stage_index
                    and not risk_requires_remedial
                    and not overlap
                ):
                    score -= 2

        driver_flags: set[str] = set()
        if overlap or declining_overlap or persistent_overlap or review_due_overlap or review_soon_overlap:
            driver_flags.add("skill")
        if (
            overlap_failed
            or (unresolved_teaching_plan and teaching_plan_overlap)
            or (achieved_teaching_plan and not teaching_plan_overlap)
            or (training_plan_overlap and training_plan_status in ("not_achieved", "partially_achieved", "no_plan"))
        ):
            driver_flags.add("continuity")
        if risk_requires_remedial and overlap:
            driver_flags.add("compliance")
        if (
            is_curriculum_stage_scenario
            or curriculum_overlap
            or fills_missing_curriculum_scenario
            or repeats_curriculum_scenario
        ):
            driver_flags.add("curriculum")
        reason_category = _reason_category(driver_flags=driver_flags)
        has_compliance_driver = "compliance" in driver_flags
        has_continuity_driver = "continuity" in driver_flags
        has_curriculum_driver = "curriculum" in driver_flags
        suggested_repetition_count = _suggested_repetition_count(
            reason_category=reason_category,
            dominant_cluster=dominant_cluster,
            persistent_overlap=persistent_overlap,
            repeated_medium_risk=repeated_medium_risk,
        )
        primary_target_subskill = (overlap or target_subskills[:1] or list(scenario.focus_subskills[:1]) or [None])[0]

        # Evidence Source & Stop Condition
        evidence_source = f"Based on {', '.join(overlap[:2])} performance trend." if overlap else "Based on overall curriculum gap."
        if recommendation_type == "continuity":
            if teaching_plan_status == "not_achieved":
                evidence_source = "Frozen teaching-plan target was not achieved in the latest review."
            elif teaching_plan_status == "partially_achieved":
                evidence_source = "Frozen teaching-plan target was only partially achieved in the latest review."
            else:
                evidence_source = f"Recurring weakness in {', '.join(failed_carryover)}."
        elif training_plan_overlap and training_plan_status in ("not_achieved", "partially_achieved"):
            if training_plan_status == "not_achieved":
                evidence_source = "Admin training-plan target was not achieved in the latest review."
            else:
                evidence_source = "Admin training-plan target was only partially achieved."
        elif recommendation_type == "compliance":
            evidence_source = (
                "Repeated medium compliance risk detected."
                if repeated_medium_risk and not has_high_risk
                else "Critical compliance risk detected."
            )
        elif fills_missing_curriculum_scenario:
            evidence_source = "Current curriculum stage still requires this scenario."
        elif repeats_curriculum_scenario:
            evidence_source = (
                "Current curriculum stage recommends another repetition before promotion."
            )
        elif review_due_overlap:
            evidence_source = f"Spaced review is due for {', '.join(review_due_overlap[:2])}."
        elif review_soon_overlap:
            evidence_source = "A stable skill is approaching its next review window."
        elif achieved_teaching_plan and not teaching_plan_overlap:
            evidence_source = "Previous frozen teaching-plan target was achieved; this path extends the next objective."

        stop_condition = _stop_condition(
            reason_category=reason_category,
            primary_target_subskill=primary_target_subskill,
            has_compliance_driver=has_compliance_driver,
            has_continuity_driver=has_continuity_driver,
            has_curriculum_driver=has_curriculum_driver,
            extends_after_achieved_teaching_plan=(
                achieved_teaching_plan
                and not teaching_plan_overlap
                and DIFFICULTY_ORDER.get(scenario.difficulty, 1)
                > DIFFICULTY_ORDER.get(current_scenario_difficulty, 1)
            ),
        )

        urgency, urgency_reason = _compute_urgency(
            has_high_risk=risk_requires_remedial,
            overall_score=overall_score,
            declining_overlap=declining_overlap,
            persistent_overlap=persistent_overlap,
            review_due_overlap=review_due_overlap,
            teaching_plan_status=teaching_plan_status,
            has_compliance_driver=has_compliance_driver,
        )

        ranked.append(
            (
                score,
                difficulty_distance,
                scenario.title.lower(),
                ScenarioRecommendation(
                    scenario_id=scenario.id,
                    title=scenario.title,
                    difficulty=scenario.difficulty,
                    target_subskills=overlap
                    or target_subskills[:2]
                    or list(scenario.focus_subskills[:2]),
                    reason=_build_reason(
                        overlap=overlap,
                        desired_difficulty=desired_difficulty,
                        scenario=scenario,
                        current_scenario_difficulty=current_scenario_difficulty,
                        diagnosis_label=diagnosis_label,
                        has_high_risk=risk_requires_remedial,
                        dominant_cluster=dominant_cluster,
                        declining_overlap=declining_overlap,
                        persistent_overlap=persistent_overlap,
                        review_due_overlap=review_due_overlap,
                        review_soon_overlap=review_soon_overlap,
                        teaching_plan_status=teaching_plan_status,
                        teaching_plan_overlap=teaching_plan_overlap,
                        curriculum_stage_title=(
                            current_curriculum_stage_title if has_curriculum_driver else None
                        ),
                        curriculum_overlap=curriculum_overlap,
                        fills_missing_curriculum_scenario=fills_missing_curriculum_scenario,
                        repeats_curriculum_scenario=repeats_curriculum_scenario,
                        parts_meta={"failed_carryover": failed_carryover},
                    ),
                    recommendation_type=recommendation_type,
                    evidence_source=evidence_source,
                    stop_condition=stop_condition,
                    expected_difficulty=scenario.difficulty,
                    suggested_repetition_count=suggested_repetition_count,
                    reason_category=reason_category,
                    urgency=urgency,
                    urgency_reason=urgency_reason,
                ),
            )
        )

    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [item[3] for item in ranked[:max_items]]
