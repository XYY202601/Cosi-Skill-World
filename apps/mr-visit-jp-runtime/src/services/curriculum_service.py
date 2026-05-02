from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scenarios.asset_loader import CurriculumRecord, CurriculumStageRecord


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


@dataclass(frozen=True)
class CurriculumScenarioProgress:
    scenario_id: str
    title: str
    attempt_count: int
    required: bool
    remaining_repetitions: int


@dataclass(frozen=True)
class CurriculumProgressState:
    curriculum_id: str
    curriculum_title: str
    current_stage_id: str
    current_stage_title: str
    current_stage_description: str
    current_module_id: str
    current_module_title: str
    stage_position: int
    total_stages: int
    status: str
    mastery_status: str
    review_status: str
    next_review_in_sessions: int | None
    target_subskills: list[str]
    recommended_repetition: int
    current_stage_scenarios: list[CurriculumScenarioProgress]
    completed_stage_ids: list[str]
    rationale: str
    next_stage_id: str | None
    next_stage_title: str | None
    attention_reason: str
    metrics: dict[str, Any]


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _scenario_attempt_counts(recent_history: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in recent_history:
        if not isinstance(item, dict):
            continue
        scenario_id = item.get("scenario_id")
        if not isinstance(scenario_id, str):
            continue
        normalized = scenario_id.strip()
        if not normalized:
            continue
        counts[normalized] = counts.get(normalized, 0) + 1
    return counts


def _evaluate_stage(
    *,
    stage: CurriculumStageRecord,
    recent_history: list[dict[str, Any]],
    subskill_signals: dict[str, dict[str, Any]],
    scenario_counts: dict[str, int],
) -> dict[str, Any]:
    stage_history = [
        item
        for item in recent_history
        if isinstance(item, dict) and item.get("scenario_id") in set(stage.scenario_ids)
    ]
    stage_scores = [
        _safe_float(item.get("overall_score"))
        for item in stage_history
        if isinstance(item, dict)
    ]
    average_stage_score = round(_average(stage_scores), 1)

    target_values = [
        _safe_float(subskill_signals.get(subskill_id, {}).get("rolling_average"))
        for subskill_id in stage.target_subskills
    ]
    target_subskill_average = round(_average(target_values), 2)

    required_scenario_ids = stage.completion_criteria.required_scenario_ids
    completed_required_scenario_ids = [
        scenario_id
        for scenario_id in required_scenario_ids
        if scenario_counts.get(scenario_id, 0) > 0
    ]
    missing_required_scenario_ids = [
        scenario_id
        for scenario_id in required_scenario_ids
        if scenario_counts.get(scenario_id, 0) <= 0
    ]

    current_stage_scenarios = [
        CurriculumScenarioProgress(
            scenario_id=scenario_id,
            title=stage.scenario_titles.get(scenario_id, scenario_id),
            attempt_count=scenario_counts.get(scenario_id, 0),
            required=scenario_id in required_scenario_ids,
            remaining_repetitions=max(
                0,
                stage.recommended_repetition - scenario_counts.get(scenario_id, 0),
            ),
        )
        for scenario_id in stage.scenario_ids
    ]

    meets_min_sessions = len(stage_history) >= stage.completion_criteria.min_completed_sessions
    meets_average_score = (
        average_stage_score >= stage.completion_criteria.min_average_overall_score
        if stage_history
        else False
    )
    meets_target_subskill_average = (
        target_subskill_average >= stage.completion_criteria.min_target_subskill_average
    )
    completed = (
        not missing_required_scenario_ids
        and meets_min_sessions
        and meets_average_score
        and meets_target_subskill_average
    )

    return {
        "completed": completed,
        "stage_history_count": len(stage_history),
        "average_stage_score": average_stage_score,
        "target_subskill_average": target_subskill_average,
        "current_stage_scenarios": current_stage_scenarios,
        "completed_required_scenario_ids": completed_required_scenario_ids,
        "missing_required_scenario_ids": missing_required_scenario_ids,
        "meets_min_sessions": meets_min_sessions,
        "meets_average_score": meets_average_score,
        "meets_target_subskill_average": meets_target_subskill_average,
    }


def _titles(stage: CurriculumStageRecord, scenario_ids: list[str]) -> list[str]:
    return [stage.scenario_titles.get(scenario_id, scenario_id) for scenario_id in scenario_ids]


def _sessions_since_stage_focus(
    *,
    stage: CurriculumStageRecord,
    recent_history: list[dict[str, Any]],
) -> int | None:
    stage_scenarios = set(stage.scenario_ids)
    for offset, item in enumerate(reversed(recent_history)):
        if not isinstance(item, dict):
            continue
        scenario_id = item.get("scenario_id")
        if scenario_id in stage_scenarios:
            return offset
    return None


def _derive_stage_mastery_status(
    *,
    stage: CurriculumStageRecord,
    status: str,
    evaluation: dict[str, Any],
    subskill_signals: dict[str, dict[str, Any]],
) -> str:
    target_statuses = [
        str(subskill_signals.get(subskill_id, {}).get("mastery_status", "needs_practice"))
        for subskill_id in stage.target_subskills
    ]
    stable_like_count = sum(1 for value in target_statuses if value in {"stable", "mastered"})
    improving_count = sum(1 for value in target_statuses if value == "improving")

    if status == "completed":
        if (
            stable_like_count == len(target_statuses)
            and evaluation["average_stage_score"]
            >= stage.completion_criteria.min_average_overall_score + 6.0
            and evaluation["target_subskill_average"]
            >= stage.completion_criteria.min_target_subskill_average + 0.4
        ):
            return "mastered"
        return "stable"

    if evaluation["stage_history_count"] <= 0:
        return "needs_practice"
    if (
        evaluation["average_stage_score"] >= stage.completion_criteria.min_average_overall_score - 6.0
        or evaluation["target_subskill_average"]
        >= stage.completion_criteria.min_target_subskill_average - 0.3
        or improving_count > 0
    ):
        return "improving"
    return "needs_practice"


def _derive_stage_review_signal(
    *,
    stage: CurriculumStageRecord,
    status: str,
    mastery_status: str,
    recent_history: list[dict[str, Any]],
    subskill_signals: dict[str, dict[str, Any]],
) -> tuple[str, int | None, str]:
    if status != "completed":
        return (
            "focus_now",
            0,
            f"{stage.title} is still the active training stage and should stay in the immediate practice loop.",
        )

    target_review_statuses = [
        str(subskill_signals.get(subskill_id, {}).get("review_status", "maintain"))
        for subskill_id in stage.target_subskills
    ]
    if "due" in target_review_statuses:
        return (
            "due",
            0,
            "One or more target subskills from this completed stage are already due for review.",
        )

    sessions_since_focus = _sessions_since_stage_focus(stage=stage, recent_history=recent_history)
    due_gap = 6 if mastery_status == "mastered" else 5
    soon_gap = 4 if mastery_status == "mastered" else 3
    remaining_sessions = due_gap if sessions_since_focus is None else max(0, due_gap - sessions_since_focus)

    if sessions_since_focus is not None and sessions_since_focus >= due_gap:
        return (
            "due",
            0,
            f"It has been {sessions_since_focus} session(s) since this stage was last practiced. Schedule a review now.",
        )
    if sessions_since_focus is not None and sessions_since_focus >= soon_gap:
        return (
            "soon",
            remaining_sessions,
            f"Plan a retention check for this stage within the next {remaining_sessions or 1} session(s).",
        )

    return (
        "maintain",
        remaining_sessions,
        f"This stage is holding steady. Revisit it in about {remaining_sessions} more session(s).",
    )


def _build_rationale(
    *,
    stage: CurriculumStageRecord,
    status: str,
    evaluation: dict[str, Any],
) -> str:
    if status == "completed":
        return (
            f"All curriculum stages are complete. Keep reinforcing {stage.title} so the final-stage "
            "behaviors stay stable under pressure."
        )

    missing_required = evaluation["missing_required_scenario_ids"]
    if missing_required:
        return (
            f"{stage.title} is still active because required scenarios are missing: "
            f"{', '.join(_titles(stage, missing_required))}."
        )

    if not evaluation["meets_min_sessions"]:
        remaining_runs = max(
            0,
            stage.completion_criteria.min_completed_sessions - int(evaluation["stage_history_count"]),
        )
        return (
            f"{stage.title} needs {remaining_runs} more finalized run(s) before promotion to the "
            "next stage."
        )

    if not evaluation["meets_average_score"]:
        return (
            f"{stage.title} stays active because the stage average {evaluation['average_stage_score']:.1f} "
            f"is below the required {stage.completion_criteria.min_average_overall_score:.1f}."
        )

    if not evaluation["meets_target_subskill_average"]:
        return (
            f"{stage.title} stays active because the target-subskill average "
            f"{evaluation['target_subskill_average']:.2f}/5 is below "
            f"{stage.completion_criteria.min_target_subskill_average:.2f}/5."
        )

    remaining_repetitions = [
        item.title
        for item in evaluation["current_stage_scenarios"]
        if item.remaining_repetitions > 0
    ]
    if remaining_repetitions:
        return (
            f"{stage.title} still recommends repetition in {', '.join(remaining_repetitions)} "
            "before moving on."
        )

    return f"{stage.title} is the current curriculum focus."


def derive_curriculum_progress(
    *,
    curriculum: CurriculumRecord,
    recent_history: list[dict[str, Any]],
    subskill_signals: dict[str, dict[str, Any]],
) -> CurriculumProgressState:
    scenario_counts = _scenario_attempt_counts(recent_history)
    completed_stage_ids: list[str] = []
    current_stage: CurriculumStageRecord | None = None
    current_evaluation: dict[str, Any] | None = None

    for stage_id in curriculum.stage_order:
        stage = curriculum.stages[stage_id]
        evaluation = _evaluate_stage(
            stage=stage,
            recent_history=recent_history,
            subskill_signals=subskill_signals,
            scenario_counts=scenario_counts,
        )
        if evaluation["completed"]:
            completed_stage_ids.append(stage_id)
            continue
        current_stage = stage
        current_evaluation = evaluation
        break

    status = "in_progress"
    if current_stage is None:
        current_stage = curriculum.stages[curriculum.stage_order[-1]]
        current_evaluation = _evaluate_stage(
            stage=current_stage,
            recent_history=recent_history,
            subskill_signals=subskill_signals,
            scenario_counts=scenario_counts,
        )
        status = "completed"

    assert current_evaluation is not None

    stage_index = curriculum.stage_index_by_id[current_stage.id]
    next_stage_id = (
        curriculum.stage_order[stage_index + 1]
        if stage_index + 1 < len(curriculum.stage_order)
        else None
    )
    next_stage_title = (
        curriculum.stages[next_stage_id].title
        if next_stage_id is not None
        else None
    )
    current_module = curriculum.modules[current_stage.module_id]
    mastery_status = _derive_stage_mastery_status(
        stage=current_stage,
        status=status,
        evaluation=current_evaluation,
        subskill_signals=subskill_signals,
    )
    review_status, next_review_in_sessions, attention_reason = _derive_stage_review_signal(
        stage=current_stage,
        status=status,
        mastery_status=mastery_status,
        recent_history=recent_history,
        subskill_signals=subskill_signals,
    )

    return CurriculumProgressState(
        curriculum_id=curriculum.id,
        curriculum_title=curriculum.title,
        current_stage_id=current_stage.id,
        current_stage_title=current_stage.title,
        current_stage_description=current_stage.description,
        current_module_id=current_module.id,
        current_module_title=current_module.title,
        stage_position=stage_index + 1,
        total_stages=len(curriculum.stage_order),
        status=status,
        mastery_status=mastery_status,
        review_status=review_status,
        next_review_in_sessions=next_review_in_sessions,
        target_subskills=list(current_stage.target_subskills),
        recommended_repetition=current_stage.recommended_repetition,
        current_stage_scenarios=list(current_evaluation["current_stage_scenarios"]),
        completed_stage_ids=list(completed_stage_ids),
        rationale=_build_rationale(
            stage=current_stage,
            status=status,
            evaluation=current_evaluation,
        ),
        next_stage_id=next_stage_id,
        next_stage_title=next_stage_title,
        attention_reason=attention_reason,
        metrics={
            "completed_sessions": int(current_evaluation["stage_history_count"]),
            "required_scenarios_completed": len(
                current_evaluation["completed_required_scenario_ids"]
            ),
            "required_scenarios_total": len(
                current_stage.completion_criteria.required_scenario_ids
            ),
            "average_stage_score": current_evaluation["average_stage_score"],
            "target_subskill_average": current_evaluation["target_subskill_average"],
        },
    )


def serialize_curriculum_progress(progress: CurriculumProgressState) -> dict[str, Any]:
    return {
        "curriculum_id": progress.curriculum_id,
        "curriculum_title": progress.curriculum_title,
        "current_stage_id": progress.current_stage_id,
        "current_stage_title": progress.current_stage_title,
        "current_stage_description": progress.current_stage_description,
        "current_module_id": progress.current_module_id,
        "current_module_title": progress.current_module_title,
        "stage_position": progress.stage_position,
        "total_stages": progress.total_stages,
        "status": progress.status,
        "mastery_status": progress.mastery_status,
        "review_status": progress.review_status,
        "next_review_in_sessions": progress.next_review_in_sessions,
        "target_subskills": list(progress.target_subskills),
        "recommended_repetition": progress.recommended_repetition,
        "current_stage_scenarios": [
            {
                "scenario_id": item.scenario_id,
                "title": item.title,
                "attempt_count": item.attempt_count,
                "required": item.required,
                "remaining_repetitions": item.remaining_repetitions,
            }
            for item in progress.current_stage_scenarios
        ],
        "completed_stage_ids": list(progress.completed_stage_ids),
        "rationale": progress.rationale,
        "next_stage_id": progress.next_stage_id,
        "next_stage_title": progress.next_stage_title,
        "attention_reason": progress.attention_reason,
        "metrics": dict(progress.metrics),
    }
