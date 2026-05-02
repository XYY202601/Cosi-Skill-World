from __future__ import annotations

from typing import Any

from scenarios.asset_loader import CurriculumRecord, CurriculumStageRecord
from services.curriculum_service import CurriculumProgressState


HIGH_RISK_COMPLIANCE_SEVERITIES = {"high", "critical"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _scenario_attempt_counts(recent_history: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in recent_history:
        if not isinstance(item, dict):
            continue
        scenario_id = item.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            continue
        counts[scenario_id.strip()] = counts.get(scenario_id.strip(), 0) + 1
    return counts


def _latest_stage_timestamp(
    *,
    stage: CurriculumStageRecord,
    recent_history: list[dict[str, Any]],
) -> str | None:
    stage_scenario_ids = set(stage.scenario_ids)
    for item in reversed(recent_history):
        if not isinstance(item, dict):
            continue
        if item.get("scenario_id") not in stage_scenario_ids:
            continue
        timestamp = item.get("timestamp")
        if isinstance(timestamp, str) and timestamp.strip():
            return timestamp.strip()
    return None


def _current_stage_progress_percent(
    *,
    stage: CurriculumStageRecord,
    curriculum_progress: CurriculumProgressState,
) -> int:
    metrics = curriculum_progress.metrics
    criteria = stage.completion_criteria
    required_total = max(1, int(metrics.get("required_scenarios_total", 0)))

    progress_parts = [
        min(1.0, _safe_float(metrics.get("completed_sessions")) / max(1, criteria.min_completed_sessions)),
        min(1.0, _safe_float(metrics.get("required_scenarios_completed")) / required_total),
        min(
            1.0,
            _safe_float(metrics.get("average_stage_score"))
            / max(1.0, criteria.min_average_overall_score),
        ),
        min(
            1.0,
            _safe_float(metrics.get("target_subskill_average"))
            / max(0.1, criteria.min_target_subskill_average),
        ),
    ]
    return int(round((sum(progress_parts) / len(progress_parts)) * 100))


def _stage_node_status(
    *,
    stage_id: str,
    curriculum_progress: CurriculumProgressState,
) -> str:
    if stage_id in curriculum_progress.completed_stage_ids:
        return "completed"
    if stage_id == curriculum_progress.current_stage_id:
        return "completed" if curriculum_progress.status == "completed" else "active"
    return "locked"


def _stage_node_progress_percent(
    *,
    stage: CurriculumStageRecord,
    status: str,
    curriculum_progress: CurriculumProgressState,
) -> int:
    if status == "completed":
        return 100
    if status == "locked":
        return 0
    return _current_stage_progress_percent(
        stage=stage,
        curriculum_progress=curriculum_progress,
    )


def _build_stage_nodes(
    *,
    curriculum: CurriculumRecord,
    curriculum_progress: CurriculumProgressState,
    recent_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scenario_counts = _scenario_attempt_counts(recent_history)
    nodes: list[dict[str, Any]] = []

    for index, stage_id in enumerate(curriculum.stage_order, start=1):
        stage = curriculum.stages[stage_id]
        status = _stage_node_status(
            stage_id=stage_id,
            curriculum_progress=curriculum_progress,
        )
        required_ids = stage.completion_criteria.required_scenario_ids
        completed_required = [
            scenario_id
            for scenario_id in required_ids
            if scenario_counts.get(scenario_id, 0) > 0
        ]
        completed_scenarios = [
            scenario_id
            for scenario_id in stage.scenario_ids
            if scenario_counts.get(scenario_id, 0) > 0
        ]
        is_current = stage_id == curriculum_progress.current_stage_id
        nodes.append(
            {
                "node_id": f"stage:{stage_id}",
                "kind": "curriculum_stage",
                "stage_id": stage_id,
                "title": stage.title,
                "description": stage.description,
                "module_id": stage.module_id,
                "position": index,
                "status": status,
                "progress_percent": _stage_node_progress_percent(
                    stage=stage,
                    status=status,
                    curriculum_progress=curriculum_progress,
                ),
                "target_subskills": list(stage.target_subskills),
                "scenario_ids": list(stage.scenario_ids),
                "completed_scenario_count": len(completed_scenarios),
                "scenario_count": len(stage.scenario_ids),
                "required_scenarios_completed": len(completed_required),
                "required_scenarios_total": len(required_ids),
                "mastery_status": curriculum_progress.mastery_status if is_current else status,
                "review_status": curriculum_progress.review_status if is_current else "maintain",
                "rationale": (
                    curriculum_progress.rationale
                    if is_current
                    else (
                        "Completed through curriculum criteria."
                        if status == "completed"
                        else "Locked until prerequisite stages are complete."
                    )
                ),
                "last_trained_at": _latest_stage_timestamp(
                    stage=stage,
                    recent_history=recent_history,
                ),
            }
        )

    return nodes


def _earned_at_for_first_session(recent_history: list[dict[str, Any]]) -> str | None:
    for item in recent_history:
        if not isinstance(item, dict):
            continue
        timestamp = item.get("timestamp")
        if isinstance(timestamp, str) and timestamp.strip():
            return timestamp.strip()
    return None


def _earned_at_for_completed_stage(
    *,
    stage: CurriculumStageRecord,
    recent_history: list[dict[str, Any]],
) -> str | None:
    return _latest_stage_timestamp(stage=stage, recent_history=recent_history)


def _has_safe_recent_streak(recent_history: list[dict[str, Any]], *, streak_length: int = 3) -> bool:
    if len(recent_history) < streak_length:
        return False
    for item in recent_history[-streak_length:]:
        if not isinstance(item, dict):
            return False
        severity = str(item.get("max_compliance_severity", "")).strip().lower()
        if severity in HIGH_RISK_COMPLIANCE_SEVERITIES:
            return False
    return True


def _latest_teaching_plan_achievement(recent_history: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in reversed(recent_history):
        if not isinstance(item, dict):
            continue
        achievement = item.get("teaching_plan_achievement")
        if isinstance(achievement, dict):
            return achievement
    return None


def _build_achievements(
    *,
    curriculum: CurriculumRecord,
    curriculum_progress: CurriculumProgressState,
    recent_history: list[dict[str, Any]],
    subskill_signals: dict[str, dict[str, Any]],
    total_sessions: int,
    updated_at: str,
) -> list[dict[str, Any]]:
    achievements: list[dict[str, Any]] = []

    if total_sessions >= 1:
        achievements.append(
            {
                "achievement_id": "first_finalized_session",
                "kind": "practice",
                "title": "First finalized visit",
                "description": "Completed the first finalized training session.",
                "status": "earned",
                "earned_at": _earned_at_for_first_session(recent_history) or updated_at,
                "evidence": {"total_sessions": total_sessions},
            }
        )

    if total_sessions >= 5:
        achievements.append(
            {
                "achievement_id": "five_session_foundation",
                "kind": "practice",
                "title": "Five-session foundation",
                "description": "Completed five finalized training sessions.",
                "status": "earned",
                "earned_at": updated_at,
                "evidence": {"total_sessions": total_sessions},
            }
        )

    for stage_id in curriculum_progress.completed_stage_ids:
        stage = curriculum.stages.get(stage_id)
        if stage is None:
            continue
        achievements.append(
            {
                "achievement_id": f"stage_completed:{stage_id}",
                "kind": "curriculum",
                "title": f"Completed {stage.title}",
                "description": "Met the stage completion criteria through finalized training evidence.",
                "status": "earned",
                "earned_at": _earned_at_for_completed_stage(stage=stage, recent_history=recent_history)
                or updated_at,
                "evidence": {
                    "stage_id": stage_id,
                    "required_scenarios": list(stage.completion_criteria.required_scenario_ids),
                },
            }
        )

    mastered_subskills = [
        subskill_id
        for subskill_id, signal in subskill_signals.items()
        if isinstance(signal, dict) and signal.get("mastery_status") == "mastered"
    ]
    for subskill_id in mastered_subskills:
        signal = subskill_signals[subskill_id]
        achievements.append(
            {
                "achievement_id": f"subskill_mastered:{subskill_id}",
                "kind": "mastery",
                "title": f"Mastered {subskill_id.replace('_', ' ')}",
                "description": "Reached the mastered threshold from rolling average and recent evidence.",
                "status": "earned",
                "earned_at": updated_at,
                "evidence": {
                    "subskill_id": subskill_id,
                    "rolling_average": signal.get("rolling_average"),
                    "history_count": signal.get("history_count"),
                },
            }
        )

    if _has_safe_recent_streak(recent_history):
        achievements.append(
            {
                "achievement_id": "safe_three_session_streak",
                "kind": "compliance",
                "title": "Three-session safe streak",
                "description": "Finished three recent sessions without high-risk compliance flags.",
                "status": "earned",
                "earned_at": updated_at,
                "evidence": {"recent_session_count": 3},
            }
        )

    teaching_plan_achievement = _latest_teaching_plan_achievement(recent_history)
    if teaching_plan_achievement is not None and teaching_plan_achievement.get("status") == "achieved":
        achievements.append(
            {
                "achievement_id": "teaching_plan_achieved",
                "kind": "teaching_plan",
                "title": "Teaching target achieved",
                "description": "The latest frozen teaching-plan target was marked achieved.",
                "status": "earned",
                "earned_at": updated_at,
                "evidence": dict(teaching_plan_achievement),
            }
        )

    return achievements


def derive_skill_world(
    *,
    curriculum: CurriculumRecord | None,
    curriculum_progress: CurriculumProgressState | None,
    recent_history: list[dict[str, Any]],
    subskill_signals: dict[str, dict[str, Any]],
    total_sessions: int,
    updated_at: str,
) -> dict[str, Any] | None:
    if curriculum is None or curriculum_progress is None:
        return None

    nodes = _build_stage_nodes(
        curriculum=curriculum,
        curriculum_progress=curriculum_progress,
        recent_history=recent_history,
    )
    achievements = _build_achievements(
        curriculum=curriculum,
        curriculum_progress=curriculum_progress,
        recent_history=recent_history,
        subskill_signals=subskill_signals,
        total_sessions=total_sessions,
        updated_at=updated_at,
    )
    completed_stage_count = len(curriculum_progress.completed_stage_ids)
    active_node = next((node for node in nodes if node["status"] == "active"), None)
    if curriculum_progress.status == "completed":
        active_node = nodes[-1] if nodes else None
    active_progress = _safe_float(active_node.get("progress_percent") if active_node else 0.0)
    total_stage_count = max(1, len(nodes))
    map_progress_percent = int(
        round(((completed_stage_count + (active_progress / 100.0)) / total_stage_count) * 100)
    )
    mastered_subskill_count = sum(
        1
        for signal in subskill_signals.values()
        if isinstance(signal, dict) and signal.get("mastery_status") == "mastered"
    )

    return {
        "version": 1,
        "map_id": f"{curriculum.id}_world_v1",
        "title": f"{curriculum.title} Skill World",
        "active_node_id": active_node.get("node_id") if active_node else None,
        "summary": {
            "completed_stage_count": completed_stage_count,
            "total_stage_count": len(nodes),
            "map_progress_percent": max(0, min(100, map_progress_percent)),
            "earned_achievement_count": len(achievements),
            "mastered_subskill_count": mastered_subskill_count,
            "total_subskill_count": len(subskill_signals),
            "current_stage_title": curriculum_progress.current_stage_title,
        },
        "nodes": nodes,
        "achievements": achievements,
    }
