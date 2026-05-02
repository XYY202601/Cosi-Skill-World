from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from persistence.interfaces import ProgressStore, ProgressStoreError
from runtime_context import DomainSessionContext
from scenarios.asset_loader import CurriculumRecord, ScenarioRecord
from services.coach_continuity import build_coach_memory
from services.curriculum_service import (
    derive_curriculum_progress,
    serialize_curriculum_progress,
)
from services.recommendation_engine import (
    ScenarioRecommendation,
    build_scenario_recommendations,
    derive_session_weak_subskills,
    summarize_weakness_clusters,
)
from services.analytics_engine import derive_performance_trends
from services.skill_world import derive_skill_world


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


SCORE_HISTORY_LIMIT = 8
TREND_DELTA_THRESHOLD = 0.35
RECENT_HISTORY_LIMIT = 1000
APPLIED_SESSION_HISTORY_LIMIT = 4000
MASTERED_MIN_HISTORY = 3
MASTERED_MIN_ROLLING_AVERAGE = 4.2
MASTERED_MIN_RECENT_SCORE = 4.0
STABLE_MIN_HISTORY = 3
STABLE_MIN_ROLLING_AVERAGE = 3.5
IMPROVING_MIN_HISTORY = 2
IMPROVING_DELTA_THRESHOLD = 0.4
REVIEW_SOON_GAP_MASTERED = 3
REVIEW_DUE_GAP_MASTERED = 5
REVIEW_SOON_GAP_STABLE = 3
REVIEW_DUE_GAP_STABLE = 4
RECENT_SCORE_DROP_ALERT = 0.75
COMPLIANCE_SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
    "positive": 0,
}


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _derive_long_window_trend(recent_scores: list[float]) -> str:
    if len(recent_scores) < 2:
        return "stable"

    if len(recent_scores) >= 6:
        previous_window = recent_scores[-6:-3]
        current_window = recent_scores[-3:]
    elif len(recent_scores) >= 4:
        split = len(recent_scores) // 2
        previous_window = recent_scores[:split]
        current_window = recent_scores[split:]
    else:
        previous_window = [recent_scores[-2]]
        current_window = [recent_scores[-1]]

    delta = _average(current_window) - _average(previous_window)
    if delta >= TREND_DELTA_THRESHOLD:
        return "improving"
    if delta <= -TREND_DELTA_THRESHOLD:
        return "declining"
    return "stable"


def _fallback_overall_band(score: int) -> str:
    if score >= 85:
        return "advanced"
    if score >= 72:
        return "proficient"
    if score >= 58:
        return "developing"
    return "emerging"


def _resolve_overall_band(review: dict[str, Any], overall_score: int) -> str:
    raw_value = review.get("overall_band")
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if normalized:
            return normalized
    return _fallback_overall_band(overall_score)


def _max_compliance_severity(severities: list[str]) -> str | None:
    if not severities:
        return None
    return max(
        severities,
        key=lambda value: (COMPLIANCE_SEVERITY_RANK.get(value, -1), value),
    )


def _recent_score_lift(recent_scores: list[float]) -> float:
    if len(recent_scores) < 2:
        return 0.0
    previous_average = _average(recent_scores[:-1])
    return round(recent_scores[-1] - previous_average, 2)


def _derive_mastery_status(progress: "SubskillProgressState") -> str:
    if (
        progress.history_count >= MASTERED_MIN_HISTORY
        and progress.rolling_average >= MASTERED_MIN_ROLLING_AVERAGE
        and progress.trend != "declining"
        and all(score >= MASTERED_MIN_RECENT_SCORE for score in progress.recent_scores[-2:])
    ):
        return "mastered"
    if (
        progress.history_count >= STABLE_MIN_HISTORY
        and progress.rolling_average >= STABLE_MIN_ROLLING_AVERAGE
        and progress.trend != "declining"
    ):
        return "stable"
    if progress.history_count >= IMPROVING_MIN_HISTORY and (
        progress.trend == "improving"
        or _recent_score_lift(progress.recent_scores) >= IMPROVING_DELTA_THRESHOLD
    ):
        return "improving"
    return "needs_practice"


def _derive_review_signal(
    *,
    mastery_status: str,
    progress: "SubskillProgressState",
    sessions_since_focus: int | None,
) -> tuple[str, int | None, str]:
    if mastery_status == "needs_practice":
        return (
            "focus_now",
            0,
            (
                f"Rolling average {progress.rolling_average:.2f}/5 is still below the stable "
                "threshold, so this skill stays in active practice."
            ),
        )

    if mastery_status == "improving":
        return (
            "focus_now",
            0,
            "Recent sessions are moving up; keep this skill in the next practice cycle.",
        )

    review_due_gap = REVIEW_DUE_GAP_MASTERED if mastery_status == "mastered" else REVIEW_DUE_GAP_STABLE
    review_soon_gap = REVIEW_SOON_GAP_MASTERED if mastery_status == "mastered" else REVIEW_SOON_GAP_STABLE
    recent_drop_detected = (
        progress.history_count >= STABLE_MIN_HISTORY
        and progress.rolling_average - progress.last_score >= RECENT_SCORE_DROP_ALERT
    )

    if progress.trend == "declining" or recent_drop_detected:
        status_label = "mastered" if mastery_status == "mastered" else "stable"
        return (
            "due",
            0,
            f"This previously {status_label} skill has started to slip and needs a retention check now.",
        )

    remaining_sessions = (
        review_due_gap
        if sessions_since_focus is None
        else max(0, review_due_gap - sessions_since_focus)
    )
    if sessions_since_focus is not None and sessions_since_focus >= review_due_gap:
        return (
            "due",
            0,
            "Enough sessions have passed since this skill was last trained. Schedule a review now.",
        )
    if sessions_since_focus is not None and sessions_since_focus >= review_soon_gap:
        return (
            "soon",
            remaining_sessions,
            f"Plan a spaced review within the next {remaining_sessions or 1} session(s).",
        )

    status_label = "mastered" if mastery_status == "mastered" else "stable"
    return (
        "maintain",
        remaining_sessions,
        f"This skill is currently {status_label}; revisit in about {remaining_sessions} more session(s).",
    )


class LearnerProgressNotFoundError(KeyError):
    pass


@dataclass
class SubskillProgressState:
    exp: int = 0
    level: int = 1
    last_score: float = 0.0
    trend: str = "stable"
    rolling_average: float = 0.0
    history_count: int = 0
    recent_scores: list[float] = field(default_factory=list)


@dataclass
class LearnerProgressState:
    learner_id: str
    total_sessions: int = 0
    total_exp: int = 0
    level: int = 1
    updated_at: str = field(default_factory=_utc_now_iso)
    applied_session_ids: list[str] = field(default_factory=list)
    latest_recommendations: list[ScenarioRecommendation] = field(default_factory=list)
    practice_path: list[ScenarioRecommendation] = field(default_factory=list)
    subskills: dict[str, SubskillProgressState] = field(default_factory=dict)
    recent_history: list[dict[str, Any]] = field(default_factory=list)
    coach_memory: dict[str, Any] = field(default_factory=dict)


class ProgressTracker:
    """
    Alpha in-memory learner progression tracker.
    Persistence-backed service can replace this implementation later.
    """

    def __init__(
        self,
        subskill_ids: list[str],
        scenario_catalog: dict[str, ScenarioRecord] | None = None,
        curriculum: CurriculumRecord | None = None,
        progress_store: ProgressStore | None = None,
    ) -> None:
        if not subskill_ids:
            raise ValueError("subskill_ids must not be empty")
        self._subskill_ids = list(subskill_ids)
        self._scenario_catalog = dict(scenario_catalog or {})
        self._curriculum = curriculum
        self._state_by_learner: dict[str, LearnerProgressState] = {}
        self._lock = Lock()
        self._progress_store = progress_store

    def _sessions_since_subskill_focus(
        self,
        *,
        subskill_id: str,
        recent_history: list[dict[str, Any]],
    ) -> int | None:
        for offset, history_item in enumerate(reversed(recent_history)):
            if not isinstance(history_item, dict):
                continue

            focus_subskills = history_item.get("focus_subskills", [])
            if isinstance(focus_subskills, list) and subskill_id in focus_subskills:
                return offset

            scenario_id = history_item.get("scenario_id")
            if isinstance(scenario_id, str):
                scenario = self._scenario_catalog.get(scenario_id)
                if scenario is not None and subskill_id in scenario.focus_subskills:
                    return offset

            for list_key in ("priority_subskills", "weak_subskills"):
                values = history_item.get(list_key, [])
                if isinstance(values, list) and subskill_id in values:
                    return offset
        return None

    def _subskill_signals(self, state: LearnerProgressState) -> dict[str, dict[str, Any]]:
        signals: dict[str, dict[str, Any]] = {}
        for subskill_id in self._subskill_ids:
            progress = state.subskills[subskill_id]
            mastery_status = _derive_mastery_status(progress)
            sessions_since_focus = self._sessions_since_subskill_focus(
                subskill_id=subskill_id,
                recent_history=state.recent_history,
            )
            review_status, next_review_in_sessions, status_reason = _derive_review_signal(
                mastery_status=mastery_status,
                progress=progress,
                sessions_since_focus=sessions_since_focus,
            )
            signals[subskill_id] = {
                "trend": progress.trend,
                "rolling_average": progress.rolling_average,
                "history_count": progress.history_count,
                "last_score": progress.last_score,
                "mastery_status": mastery_status,
                "review_status": review_status,
                "sessions_since_focus": sessions_since_focus,
                "next_review_in_sessions": next_review_in_sessions,
                "status_reason": status_reason,
                "recent_score_lift": _recent_score_lift(progress.recent_scores),
            }
        return signals

    def apply_session_result(
        self,
        *,
        learner_id: str | None = None,
        session_id: str | None = None,
        scenario_id: str | None = None,
        scenario_title: str,
        scenario_difficulty: str,
        focus_subskills: list[str],
        persona_id: str,
        persona_label: str,
        finish_reason: str | None = None,
        review: dict[str, Any],
        session_context: DomainSessionContext | None = None,
    ) -> dict[str, Any]:
        resolved_context = session_context
        resolved_learner_id = (
            resolved_context.learner_id if resolved_context is not None else str(learner_id or "")
        )
        resolved_session_id = (
            resolved_context.session_id if resolved_context is not None else str(session_id or "")
        )
        resolved_scenario_id = (
            resolved_context.scenario_id if resolved_context is not None else str(scenario_id or "")
        )
        if not resolved_learner_id:
            raise ValueError("learner_id must not be empty")
        if not resolved_session_id:
            raise ValueError("session_id must not be empty")
        if not resolved_scenario_id:
            raise ValueError("scenario_id must not be empty")

        with self._lock:
            state = self._state_by_learner.get(resolved_learner_id)
            if state is None:
                state = self._load_from_store(resolved_learner_id, org_id=resolved_context.org_id if resolved_context else None)
            if state is None:
                state = LearnerProgressState(
                    learner_id=resolved_learner_id,
                    subskills={
                        subskill_id: SubskillProgressState()
                        for subskill_id in self._subskill_ids
                    },
                )
                self._state_by_learner[resolved_learner_id] = state
            elif resolved_session_id in state.applied_session_ids:
                return self._serialize(state)

            overall_score = int(review.get("overall_score", 0))
            overall_band = _resolve_overall_band(review, overall_score)
            difficulty_base = {"easy": 20, "medium": 30, "hard": 40}.get(scenario_difficulty, 25)
            performance_bonus = max(0, round(overall_score * 0.2))
            exp_gain = difficulty_base + performance_bonus

            review_subskills = review.get("subskills", {})
            focus_set = set(focus_subskills)
            for subskill_id in self._subskill_ids:
                subskill_payload = review_subskills.get(subskill_id, {})
                raw_score = subskill_payload.get("score", 0)
                score = float(raw_score) if isinstance(raw_score, (int, float)) else 0.0

                progress = state.subskills[subskill_id]
                subskill_exp_gain = int(round((2 + score) * (1.2 if subskill_id in focus_set else 0.8)))
                progress.exp += subskill_exp_gain
                progress.level = 1 + progress.exp // 30
                progress.last_score = round(score, 2)
                progress.recent_scores.append(round(score, 2))
                if len(progress.recent_scores) > SCORE_HISTORY_LIMIT:
                    progress.recent_scores = progress.recent_scores[-SCORE_HISTORY_LIMIT:]
                progress.history_count = len(progress.recent_scores)
                progress.rolling_average = round(_average(progress.recent_scores), 2)
                progress.trend = _derive_long_window_trend(progress.recent_scores)

            focus_subskill_scores = {
                subskill_id: round(float(review_subskills[subskill_id].get("score", 0.0)), 2)
                for subskill_id in focus_subskills
                if isinstance(review_subskills.get(subskill_id), dict)
                and isinstance(review_subskills[subskill_id].get("score"), (int, float))
            }
            focus_subskill_average = round(_average(list(focus_subskill_scores.values())), 2)

            session_weak_subskills = derive_session_weak_subskills(
                review,
                focus_subskills,
                max_items=4,
            )
            diagnosis_payload = review.get("diagnosis", {})
            diagnosis_primary = (
                diagnosis_payload.get("primary", [])
                if isinstance(diagnosis_payload, dict)
                else []
            )
            compliance_flags = review.get("compliance_flags", [])
            compliance_severities = [
                str(item.get("severity", "")).strip().lower()
                for item in compliance_flags
                if isinstance(item, dict) and isinstance(item.get("severity"), str)
            ]
            continuity_channel = review.get("continuity_channel", {})
            teaching_plan_achievement = (
                continuity_channel.get("teaching_plan_achievement")
                if isinstance(continuity_channel, dict)
                and isinstance(continuity_channel.get("teaching_plan_achievement"), dict)
                else None
            )
            teaching_plan_snapshot = (
                resolved_context.continuity_context.get("teaching_plan_snapshot")
                if resolved_context is not None
                and isinstance(resolved_context.continuity_context.get("teaching_plan_snapshot"), dict)
                else None
            )
            frozen_teaching_plan = (
                resolved_context.continuity_context.get("teaching_plan")
                if resolved_context is not None
                and isinstance(resolved_context.continuity_context.get("teaching_plan"), dict)
                else None
            )
            frozen_training_plan = (
                resolved_context.continuity_context.get("training_plan")
                if resolved_context is not None
                and isinstance(resolved_context.continuity_context.get("training_plan"), dict)
                else None
            )

            state.total_sessions += 1
            state.total_exp += exp_gain
            state.level = 1 + state.total_exp // 120
            state.updated_at = _utc_now_iso()

            state.recent_history.append(
                {
                    "session_id": resolved_session_id,
                    "scenario_id": resolved_scenario_id,
                    "scenario_title": scenario_title,
                    "difficulty": scenario_difficulty,
                    "persona_id": persona_id,
                    "persona_label": persona_label,
                    "skill_id": resolved_context.skill_id if resolved_context is not None else "",
                    "prompt_profile": (
                        resolved_context.prompt_profile if resolved_context is not None else "unknown"
                    ),
                    "experiment_id": (
                        resolved_context.experiment_id if resolved_context is not None else None
                    ),
                    "trace_id": resolved_context.trace_id if resolved_context is not None else "",
                    "finish_reason": finish_reason or "manual_finish",
                    "overall_score": overall_score,
                    "overall_band": overall_band,
                    "exp_gain": exp_gain,
                    "focus_subskills": list(dict.fromkeys(focus_subskills))[:4],
                    "focus_subskill_scores": focus_subskill_scores,
                    "focus_subskill_average": focus_subskill_average,
                    "weak_subskills": session_weak_subskills,
                    "priority_subskills": [
                        item
                        for item in review.get("priority_subskills", [])
                        if isinstance(item, str)
                    ][:3],
                    "diagnosis_summaries": [
                        item.get("summary")
                        for item in diagnosis_primary
                        if isinstance(item, dict) and isinstance(item.get("summary"), str)
                    ][:3],
                    "max_compliance_severity": _max_compliance_severity(compliance_severities),
                    "compliance_severities": compliance_severities,
                    "teaching_plan_achievement": teaching_plan_achievement,
                    "teaching_plan_snapshot_id": (
                        str(teaching_plan_snapshot.get("snapshot_id", ""))
                        if isinstance(teaching_plan_snapshot, dict)
                        else None
                    ),
                    "timestamp": state.updated_at,
                }
            )
            if len(state.recent_history) > RECENT_HISTORY_LIMIT:
                state.recent_history = state.recent_history[-RECENT_HISTORY_LIMIT:]

            weakest_subskills = sorted(
                self._subskill_ids,
                key=lambda skill_id: (
                    0 if state.subskills[skill_id].trend == "declining" else 1,
                    state.subskills[skill_id].rolling_average,
                    state.subskills[skill_id].last_score,
                    skill_id,
                ),
            )
            subskill_signals = self._subskill_signals(state)
            curriculum_progress = (
                derive_curriculum_progress(
                    curriculum=self._curriculum,
                    recent_history=state.recent_history,
                    subskill_signals=subskill_signals,
                )
                if self._curriculum is not None
                else None
            )
            practice_path = build_scenario_recommendations(
                scenarios=self._scenario_catalog,
                current_scenario_id=resolved_scenario_id,
                current_scenario_difficulty=scenario_difficulty,
                review=review,
                recent_history=state.recent_history,
                subskill_trends={
                    subskill_id: state.subskills[subskill_id].trend
                    for subskill_id in self._subskill_ids
                },
                fallback_subskills=weakest_subskills,
                frozen_teaching_plan=frozen_teaching_plan,
                frozen_training_plan=frozen_training_plan,
                subskill_signals=subskill_signals,
                curriculum=self._curriculum,
                curriculum_progress=curriculum_progress,
            )
            state.practice_path = practice_path
            state.latest_recommendations = list(practice_path)
            state.coach_memory = build_coach_memory(
                review=review,
                recent_history=state.recent_history,
                subskill_signals=subskill_signals,
                updated_at=state.updated_at,
            )
            state.applied_session_ids.append(resolved_session_id)
            if len(state.applied_session_ids) > APPLIED_SESSION_HISTORY_LIMIT:
                state.applied_session_ids = state.applied_session_ids[-APPLIED_SESSION_HISTORY_LIMIT:]

            payload = self._serialize(state)
            if self._progress_store is not None:
                self._progress_store.upsert(
                    resolved_learner_id,
                    self._serialize(state, include_internal=True),
                    org_id=resolved_context.org_id if resolved_context else None
                )
            return payload

    def get_snapshot(self, learner_id: str, *, org_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            state = self._state_by_learner.get(learner_id)
            if state is None:
                loaded = self._load_from_store(learner_id, org_id=org_id)
                if loaded is None:
                    raise LearnerProgressNotFoundError(
                        f"No progress snapshot for learner_id: {learner_id}"
                    )
                self._state_by_learner[learner_id] = loaded
                state = loaded
            return self._serialize(state)

    def _load_from_store(self, learner_id: str, *, org_id: str | None = None) -> LearnerProgressState | None:
        if self._progress_store is None:
            return None
        try:
            payload = self._progress_store.get(learner_id, org_id=org_id)
        except ProgressStoreError as exc:
            raise ValueError(f"Failed to load progress from store: {exc}") from exc
        if payload is None:
            return None
        return self._deserialize(payload)

    def _serialize(
        self,
        state: LearnerProgressState,
        include_internal: bool = False,
    ) -> dict[str, Any]:
        subskill_signals = self._subskill_signals(state)
        curriculum_progress = (
            derive_curriculum_progress(
                curriculum=self._curriculum,
                recent_history=state.recent_history,
                subskill_signals=subskill_signals,
            )
            if self._curriculum is not None
            else None
        )
        skill_world = derive_skill_world(
            curriculum=self._curriculum,
            curriculum_progress=curriculum_progress,
            recent_history=state.recent_history,
            subskill_signals=subskill_signals,
            total_sessions=state.total_sessions,
            updated_at=state.updated_at,
        )
        payload = {
            "learner_id": state.learner_id,
            "total_sessions": state.total_sessions,
            "total_exp": state.total_exp,
            "level": state.level,
            "updated_at": state.updated_at,
            "latest_recommendations": [
                self._serialize_recommendation(item)
                for item in state.latest_recommendations
            ],
            "practice_path": [
                {
                    "step_index": index + 1,
                    **self._serialize_recommendation(item),
                }
                for index, item in enumerate(state.practice_path)
            ],
            "weakness_clusters": [
                {
                    "cluster_id": item.cluster_id,
                    "subskills": list(item.subskills),
                    "occurrences": item.occurrences,
                    "last_seen_at": item.last_seen_at,
                }
                for item in summarize_weakness_clusters(state.recent_history)
            ],
            "subskills": {
                subskill_id: {
                    "exp": payload.exp,
                    "level": payload.level,
                    "last_score": payload.last_score,
                    "trend": payload.trend,
                    "rolling_average": payload.rolling_average,
                    "history_count": payload.history_count,
                    "mastery_status": subskill_signals[subskill_id]["mastery_status"],
                    "review_status": subskill_signals[subskill_id]["review_status"],
                    "sessions_since_focus": subskill_signals[subskill_id]["sessions_since_focus"],
                    "next_review_in_sessions": subskill_signals[subskill_id]["next_review_in_sessions"],
                    "status_reason": subskill_signals[subskill_id]["status_reason"],
                    **(
                        {"recent_scores": list(payload.recent_scores)}
                        if include_internal
                        else {}
                    ),
                }
                for subskill_id, payload in state.subskills.items()
            },
            "recent_history": list(state.recent_history),
            "coach_memory": dict(state.coach_memory),
            **(
                {"curriculum": serialize_curriculum_progress(curriculum_progress)}
                if curriculum_progress is not None
                else {}
            ),
            **({"skill_world": skill_world} if skill_world is not None else {}),
            "performance_analytics": derive_performance_trends(state.recent_history),
        }
        if include_internal:
            payload["applied_session_ids"] = list(state.applied_session_ids)
        return payload

    def _deserialize(self, payload: dict[str, Any]) -> LearnerProgressState:
        try:
            learner_id = str(payload["learner_id"])
            subskills_payload = payload.get("subskills", {})
            if not isinstance(subskills_payload, dict):
                raise ValueError("subskills must be an object")

            subskills: dict[str, SubskillProgressState] = {}
            for subskill_id in self._subskill_ids:
                item = subskills_payload.get(subskill_id, {})
                if not isinstance(item, dict):
                    item = {}
                recent_scores_payload = item.get("recent_scores", [])
                recent_scores = (
                    [float(value) for value in recent_scores_payload if isinstance(value, (int, float))]
                    if isinstance(recent_scores_payload, list)
                    else []
                )[-SCORE_HISTORY_LIMIT:]
                subskills[subskill_id] = SubskillProgressState(
                    exp=int(item.get("exp", 0)),
                    level=int(item.get("level", 1)),
                    last_score=float(item.get("last_score", 0.0)),
                    trend=str(item.get("trend", "stable")),
                    rolling_average=float(item.get("rolling_average", 0.0)),
                    history_count=int(item.get("history_count", len(recent_scores))),
                    recent_scores=recent_scores,
                )

            recent_history = payload.get("recent_history", [])
            if not isinstance(recent_history, list):
                recent_history = []

            applied_session_ids = payload.get("applied_session_ids", [])
            if not isinstance(applied_session_ids, list):
                applied_session_ids = []

            latest_recommendations = payload.get("latest_recommendations", [])
            if not isinstance(latest_recommendations, list):
                latest_recommendations = []
            practice_path = payload.get("practice_path", [])
            if not isinstance(practice_path, list):
                practice_path = []

            coach_memory = payload.get("coach_memory", {})
            if not isinstance(coach_memory, dict):
                coach_memory = {}

            return LearnerProgressState(
                learner_id=learner_id,
                total_sessions=int(payload.get("total_sessions", 0)),
                total_exp=int(payload.get("total_exp", 0)),
                level=int(payload.get("level", 1)),
                updated_at=str(payload.get("updated_at", _utc_now_iso())),
                applied_session_ids=[
                    str(item) for item in applied_session_ids if isinstance(item, str)
                ][-APPLIED_SESSION_HISTORY_LIMIT:],
                latest_recommendations=self._deserialize_recommendations(latest_recommendations),
                practice_path=self._deserialize_recommendations(practice_path or latest_recommendations),
                subskills=subskills,
                recent_history=[
                    item for item in recent_history if isinstance(item, dict)
                ][-RECENT_HISTORY_LIMIT:],
                coach_memory=coach_memory,
            )
        except Exception as exc:
            raise ValueError(f"Corrupted progress payload: {exc}") from exc

    def _deserialize_recommendations(
        self,
        payload: list[Any],
    ) -> list[ScenarioRecommendation]:
        recommendations: list[ScenarioRecommendation] = []
        for item in payload:
            if isinstance(item, str):
                scenario_id = item.strip()
                if not scenario_id:
                    continue
                scenario = self._scenario_catalog.get(scenario_id)
                recommendations.append(
                    ScenarioRecommendation(
                        scenario_id=scenario_id,
                        title=scenario.title if scenario is not None else scenario_id,
                        difficulty=scenario.difficulty if scenario is not None else "unknown",
                        target_subskills=list(scenario.focus_subskills[:2]) if scenario else [],
                        reason="Legacy recommendation carried forward from an older progress snapshot.",
                    )
                )
                continue

            if not isinstance(item, dict):
                continue

            scenario_id = str(item.get("scenario_id", "")).strip()
            if not scenario_id:
                continue

            scenario = self._scenario_catalog.get(scenario_id)
            title = str(item.get("title", "")).strip()
            difficulty = str(item.get("difficulty", "")).strip()
            raw_target_subskills = item.get("target_subskills", [])
            target_subskills = (
                [str(value) for value in raw_target_subskills if isinstance(value, str)]
                if isinstance(raw_target_subskills, list)
                else []
            )
            reason = str(item.get("reason", "")).strip()

            recommendations.append(
                ScenarioRecommendation(
                    scenario_id=scenario_id,
                    title=title or (scenario.title if scenario is not None else scenario_id),
                    difficulty=difficulty or (scenario.difficulty if scenario is not None else "unknown"),
                    target_subskills=target_subskills
                    or (list(scenario.focus_subskills[:2]) if scenario is not None else []),
                    reason=reason
                    or "Recovered recommendation payload from persisted learner progress.",
                    recommendation_type=str(item.get("recommendation_type", "skill")),
                    evidence_source=item.get("evidence_source"),
                    stop_condition=item.get("stop_condition"),
                    expected_difficulty=(
                        str(item.get("expected_difficulty")).strip()
                        if isinstance(item.get("expected_difficulty"), str)
                        and str(item.get("expected_difficulty")).strip()
                        else None
                    ),
                    suggested_repetition_count=max(
                        1,
                        int(item.get("suggested_repetition_count", 1))
                        if isinstance(item.get("suggested_repetition_count"), (int, float))
                        else 1,
                    ),
                    reason_category=str(item.get("reason_category", "skill")),
                )
            )

        return recommendations[:3]

    def _serialize_recommendation(self, item: ScenarioRecommendation) -> dict[str, Any]:
        return {
            "scenario_id": item.scenario_id,
            "title": item.title,
            "difficulty": item.difficulty,
            "target_subskills": list(item.target_subskills),
            "reason": item.reason,
            "recommendation_type": item.recommendation_type,
            "evidence_source": item.evidence_source,
            "stop_condition": item.stop_condition,
            "expected_difficulty": item.expected_difficulty,
            "suggested_repetition_count": item.suggested_repetition_count,
            "reason_category": item.reason_category,
            "urgency": item.urgency,
            "urgency_reason": item.urgency_reason,
        }
