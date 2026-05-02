from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _ensure_evaluation_core_path() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    eval_core_src = repo_root / "packages" / "evaluation-core" / "src"
    eval_core_src_str = str(eval_core_src)
    if eval_core_src_str not in sys.path:
        sys.path.insert(0, eval_core_src_str)


_ensure_evaluation_core_path()

from evaluation_core.mr_visit_jp import ReviewBuildInputs, build_review_payload  # noqa: E402


def build_runtime_review(
    *,
    turns: list[dict[str, Any]],
    turn_count: int,
    finish_reason: str,
    scenario_focus_subskills: list[str],
    subskill_weights: dict[str, float],
    skill_model: dict[str, Any],
    diagnosis_types: dict[str, Any],
    compliance_rules: dict[str, Any],
    score_schema: dict[str, Any],
    judge_review_schema: dict[str, Any],
    coach_feedback_schema: dict[str, Any],
    compliance_flags_schema: dict[str, Any],
    model_artifacts: dict[str, Any] | None = None,
    model_error: str | None = None,
    model_meta: dict[str, Any] | None = None,
    prompting_meta: dict[str, Any] | None = None,
    session_context_meta: dict[str, Any] | None = None,
    continuity_context: dict[str, Any] | None = None,
    scenario_id: str | None = None,
) -> dict[str, Any]:
    resolved_scenario_id = scenario_id
    if resolved_scenario_id is None and isinstance(session_context_meta, dict):
        resolved_scenario_id = session_context_meta.get("scenario_id")

    payload = build_review_payload(
        ReviewBuildInputs(
            turns=turns,
            turn_count=turn_count,
            finish_reason=finish_reason,
            scenario_focus_subskills=scenario_focus_subskills,
            subskill_weights=subskill_weights,
            skill_model=skill_model,
            diagnosis_types=diagnosis_types,
            compliance_rules=compliance_rules,
            score_schema=score_schema,
            judge_review_schema=judge_review_schema,
            coach_feedback_schema=coach_feedback_schema,
            compliance_flags_schema=compliance_flags_schema,
            model_artifacts=model_artifacts,
            model_error=model_error,
            model_meta=model_meta,
            prompting_meta=prompting_meta,
            continuity_context=continuity_context,
            scenario_id=resolved_scenario_id,
        )
    )
    meta = payload.setdefault("meta", {})
    if isinstance(meta, dict) and isinstance(session_context_meta, dict):
        meta["context"] = dict(session_context_meta)
    return payload
