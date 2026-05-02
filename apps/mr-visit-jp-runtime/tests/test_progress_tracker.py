from __future__ import annotations

from runtime_context import DomainSessionContext
from scenarios.asset_loader import get_domain_bundle
from services.progress_tracker import ProgressTracker


def _sample_review(
    subskill_ids: list[str],
    *,
    overall_score: int = 72,
    overall_band: str | None = None,
    priority_subskills: list[str] | None = None,
    diagnosis_focus: list[str] | None = None,
    low_scores: dict[str, float] | None = None,
    compliance_flags: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    priority_subskills = priority_subskills or ["opening", "scientific_delivery"]
    diagnosis_focus = diagnosis_focus or ["scientific_delivery"]
    low_scores = low_scores or {"opening": 2}

    subskills: dict[str, dict[str, object]] = {}
    for subskill_id in subskill_ids:
        score = float(low_scores.get(subskill_id, 3))
        subskills[subskill_id] = {"score": score, "evidence": ["fixture"]}

    return {
        "overall_score": overall_score,
        "overall_band": overall_band or "functional",
        "priority_subskills": list(priority_subskills),
        "diagnosis": {
            "primary": [
                {
                    "id": "synthetic_gap",
                    "recommendation_focus": list(diagnosis_focus),
                    "related_subskills": list(diagnosis_focus),
                }
            ]
        },
        "compliance_flags": compliance_flags or [],
        "subskills": subskills,
    }


def _uniform_scores(subskill_ids: list[str], score: float) -> dict[str, float]:
    return {subskill_id: score for subskill_id in subskill_ids}


def test_progress_tracker_deduplicates_retried_session_result() -> None:
    bundle = get_domain_bundle()
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
    )
    scenario = bundle.scenarios["busy_doctor_short_visit"]
    persona = bundle.personas[scenario.doctor_persona_id]

    first = tracker.apply_session_result(
        learner_id="learner_tracker_001",
        session_id="sess_tracker_retry",
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        scenario_difficulty="easy",
        focus_subskills=["opening", "scientific_delivery", "closing_followup"],
        persona_id=scenario.doctor_persona_id,
        persona_label=str(persona["label"]),
        review=_sample_review(list(bundle.manifest["subskills"])),
    )
    second = tracker.apply_session_result(
        learner_id="learner_tracker_001",
        session_id="sess_tracker_retry",
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        scenario_difficulty="easy",
        focus_subskills=["opening", "scientific_delivery", "closing_followup"],
        persona_id=scenario.doctor_persona_id,
        persona_label=str(persona["label"]),
        review=_sample_review(list(bundle.manifest["subskills"])),
    )

    assert first["total_sessions"] == 1
    assert second["total_sessions"] == 1
    assert first["total_exp"] == second["total_exp"]
    assert second["learner_id"] == "learner_tracker_001"
    assert len(second["latest_recommendations"]) > 0
    assert len(second["practice_path"]) > 0
    assert second["practice_path"][0]["step_index"] == 1
    assert second["practice_path"][0]["scenario_id"] == second["latest_recommendations"][0]["scenario_id"]
    assert second["practice_path"][0]["suggested_repetition_count"] >= 1
    assert second["practice_path"][0]["reason_category"] in {
        "skill",
        "compliance",
        "continuity",
        "mixed",
        "curriculum",
    }
    assert "weakness_clusters" in second
    assert second["coach_memory"]["last_session"]["scenario_title"] == scenario.title
    assert second["coach_memory"]["teaching_plan"]["prior_evidence"][0]["summary"] == "fixture"
    assert second["recent_history"][-1]["finish_reason"] == "manual_finish"
    assert "applied_session_ids" not in second


def test_progress_tracker_uses_long_window_trends_and_weakness_clusters() -> None:
    bundle = get_domain_bundle()
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
    )

    session_specs = [
        (
            "sess_cluster_001",
            "new_product_adoption_barrier",
            "medium",
            _sample_review(
                list(bundle.manifest["subskills"]),
                overall_score=70,
                priority_subskills=["scientific_delivery", "objection_handling"],
                diagnosis_focus=["scientific_delivery", "objection_handling"],
                low_scores={"scientific_delivery": 4, "objection_handling": 3},
            ),
        ),
        (
            "sess_cluster_002",
            "skeptical_doctor_competitor_pressure",
            "medium",
            _sample_review(
                list(bundle.manifest["subskills"]),
                overall_score=58,
                priority_subskills=["scientific_delivery", "objection_handling"],
                diagnosis_focus=["scientific_delivery", "objection_handling"],
                low_scores={"scientific_delivery": 2, "objection_handling": 2},
            ),
        ),
        (
            "sess_cluster_003",
            "revisit_after_prior_rejection",
            "medium",
            _sample_review(
                list(bundle.manifest["subskills"]),
                overall_score=46,
                priority_subskills=["scientific_delivery", "objection_handling"],
                diagnosis_focus=["scientific_delivery", "objection_handling"],
                low_scores={"scientific_delivery": 1, "objection_handling": 1},
            ),
        ),
    ]

    snapshot: dict[str, object] | None = None
    for session_id, scenario_id, difficulty, review in session_specs:
        scenario = bundle.scenarios[scenario_id]
        persona = bundle.personas[scenario.doctor_persona_id]
        snapshot = tracker.apply_session_result(
            learner_id="learner_tracker_cluster",
            session_id=session_id,
            scenario_id=scenario_id,
            scenario_title=scenario.title,
            scenario_difficulty=difficulty,
            focus_subskills=list(bundle.scenarios[scenario_id].focus_subskills),
            persona_id=scenario.doctor_persona_id,
            persona_label=str(persona["label"]),
            review=review,
        )

    assert snapshot is not None

    subskills = snapshot["subskills"]
    scientific_delivery = subskills["scientific_delivery"]
    objection_handling = subskills["objection_handling"]
    assert scientific_delivery["trend"] == "declining"
    assert scientific_delivery["rolling_average"] < 2.6
    assert scientific_delivery["history_count"] == 3
    assert objection_handling["rolling_average"] <= 2.0

    weakness_clusters = snapshot["weakness_clusters"]
    assert len(weakness_clusters) > 0
    assert weakness_clusters[0]["subskills"] == ["objection_handling", "scientific_delivery"]
    assert weakness_clusters[0]["occurrences"] >= 2

    recommendations = snapshot["latest_recommendations"]
    assert len(recommendations) > 0
    assert 1 <= len(snapshot["practice_path"]) <= 3
    assert snapshot["practice_path"][0]["step_index"] == 1
    assert snapshot["practice_path"][0]["scenario_id"] == recommendations[0]["scenario_id"]
    assert snapshot["practice_path"][0]["suggested_repetition_count"] >= 1
    assert snapshot["practice_path"][0]["expected_difficulty"] in {"easy", "medium", "hard"}
    assert recommendations[0]["scenario_id"] in {
        "cautious_doctor_evidence_check",
        "formulary_restriction_negotiation",
    }
    assert "recurring" in recommendations[0]["reason"].lower()
    assert "longer-window" in recommendations[0]["reason"].lower()

    coach_memory = snapshot["coach_memory"]
    assert "scientific_delivery" in coach_memory["active_focus_subskills"]
    assert len(coach_memory["next_actions"]) > 0
    assert len(coach_memory["recent_personas"]) > 0
    assert len(coach_memory["teaching_plan"]["prior_evidence"]) > 0


def test_progress_tracker_recent_history_exposes_filterable_review_meta() -> None:
    bundle = get_domain_bundle()
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
    )
    scenario = bundle.scenarios["adverse_event_followup_required"]
    persona = bundle.personas[scenario.doctor_persona_id]

    snapshot = tracker.apply_session_result(
        learner_id="learner_tracker_meta",
        session_id="sess_tracker_meta",
        scenario_id=scenario.id,
        scenario_title=scenario.title,
        scenario_difficulty=scenario.difficulty,
        focus_subskills=list(scenario.focus_subskills),
        persona_id=scenario.doctor_persona_id,
        persona_label=str(persona["label"]),
        review=_sample_review(
            list(bundle.manifest["subskills"]),
            overall_score=54,
            overall_band="critical_gap",
            priority_subskills=["opening", "closing_followup"],
            diagnosis_focus=["opening", "closing_followup"],
            low_scores={"opening": 1, "closing_followup": 1},
            compliance_flags=[
                {"severity": "medium"},
                {"severity": "critical"},
            ],
        ),
        session_context=DomainSessionContext(
            skill_id="mr_visit_jp",
            capability_id="practice_session",
            action_id="finish_session",
            session_id="sess_tracker_meta",
            learner_id="learner_tracker_meta",
            scenario_id=scenario.id,
            persona_id=scenario.doctor_persona_id,
            prompt_profile="alpha_coach_concise_v1",
            experiment_id="exp_review_filters",
            trace_id="trace_tracker_meta",
        ),
    )

    latest = snapshot["recent_history"][-1]
    assert latest["overall_band"] == "critical_gap"
    assert latest["prompt_profile"] == "alpha_coach_concise_v1"
    assert latest["experiment_id"] == "exp_review_filters"
    assert latest["max_compliance_severity"] == "critical"


def test_progress_tracker_curriculum_stage_explains_progress_and_respects_stage_order() -> None:
    bundle = get_domain_bundle()
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        curriculum=bundle.curriculum,
    )

    snapshot: dict[str, object] | None = None
    for session_id, scenario_id in (
        ("sess_curriculum_001", "busy_doctor_short_visit"),
        ("sess_curriculum_002", "low_interest_doctor_intro_fail"),
    ):
        scenario = bundle.scenarios[scenario_id]
        persona = bundle.personas[scenario.doctor_persona_id]
        snapshot = tracker.apply_session_result(
            learner_id="learner_curriculum_001",
            session_id=session_id,
            scenario_id=scenario_id,
            scenario_title=scenario.title,
            scenario_difficulty=scenario.difficulty,
            focus_subskills=list(scenario.focus_subskills),
            persona_id=scenario.doctor_persona_id,
            persona_label=str(persona["label"]),
            review=_sample_review(
                list(bundle.manifest["subskills"]),
                overall_score=80,
                priority_subskills=["profiling", "need_discovery"],
                diagnosis_focus=["profiling", "need_discovery"],
                low_scores={
                    subskill_id: 4
                    for subskill_id in bundle.manifest["subskills"]
                },
            ),
        )

    assert snapshot is not None

    curriculum = snapshot["curriculum"]
    assert curriculum["current_stage_id"] == "foundation_context_reentry"
    assert curriculum["current_stage_title"] == "Stage 2. Re-entry And Niche Discovery"
    assert curriculum["completed_stage_ids"] == ["foundation_concise_entry"]
    assert "required scenarios are missing" in curriculum["rationale"].lower()
    assert curriculum["mastery_status"] == "needs_practice"
    assert curriculum["review_status"] == "focus_now"
    assert "active training stage" in curriculum["attention_reason"].lower()
    assert curriculum["metrics"]["required_scenarios_completed"] == 0
    assert curriculum["metrics"]["required_scenarios_total"] == 2

    skill_world = snapshot["skill_world"]
    assert skill_world["summary"]["completed_stage_count"] == 1
    assert skill_world["summary"]["total_stage_count"] == len(bundle.curriculum.stage_order)
    assert skill_world["summary"]["map_progress_percent"] > 25
    assert len(skill_world["nodes"]) == len(bundle.curriculum.stage_order)
    assert skill_world["nodes"][0]["status"] == "completed"
    assert skill_world["nodes"][1]["status"] == "active"
    assert skill_world["active_node_id"] == "stage:foundation_context_reentry"
    achievement_ids = {item["achievement_id"] for item in skill_world["achievements"]}
    assert "first_finalized_session" in achievement_ids
    assert "stage_completed:foundation_concise_entry" in achievement_ids

    recommendations = snapshot["latest_recommendations"]
    assert [item["scenario_id"] for item in recommendations[:2]] == [
        "revisit_after_prior_rejection",
        "new_product_adoption_barrier",
    ]
    assert recommendations[0]["reason_category"] == "mixed"
    assert "fits the current curriculum stage" in recommendations[0]["reason"].lower()
    assert "required stage scenario" in recommendations[0]["reason"].lower()
    assert recommendations[0]["evidence_source"] == (
        "Current curriculum stage still requires this scenario."
    )


def test_progress_tracker_exposes_mastery_and_review_schedule_after_focus_gap() -> None:
    bundle = get_domain_bundle()
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        curriculum=bundle.curriculum,
    )

    session_order = [
        "busy_doctor_short_visit",
        "low_interest_doctor_intro_fail",
        "revisit_after_prior_rejection",
        "cautious_doctor_evidence_check",
        "formulary_restriction_negotiation",
        "adverse_event_followup_required",
        "new_product_adoption_barrier",
        "skeptical_doctor_competitor_pressure",
    ]

    snapshot: dict[str, object] | None = None
    for index, scenario_id in enumerate(session_order, start=1):
        scenario = bundle.scenarios[scenario_id]
        persona = bundle.personas[scenario.doctor_persona_id]
        snapshot = tracker.apply_session_result(
            learner_id="learner_mastery_gap_001",
            session_id=f"sess_mastery_gap_{index:03d}",
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            scenario_difficulty=scenario.difficulty,
            focus_subskills=list(scenario.focus_subskills),
            persona_id=scenario.doctor_persona_id,
            persona_label=str(persona["label"]),
            review=_sample_review(
                list(bundle.manifest["subskills"]),
                overall_score=88,
                priority_subskills=list(scenario.focus_subskills[:2]),
                diagnosis_focus=list(scenario.focus_subskills[:2]),
                low_scores=_uniform_scores(list(bundle.manifest["subskills"]), 5),
            ),
        )

    assert snapshot is not None

    opening = snapshot["subskills"]["opening"]
    assert opening["mastery_status"] == "mastered"
    assert opening["review_status"] == "due"
    assert opening["sessions_since_focus"] == 5
    assert opening["next_review_in_sessions"] == 0
    assert "review now" in opening["status_reason"].lower()

    latest_history = snapshot["recent_history"][-1]
    assert latest_history["focus_subskill_average"] == 5.0
    assert latest_history["focus_subskill_scores"]["profiling"] == 5.0

    curriculum = snapshot["curriculum"]
    assert curriculum["mastery_status"] in {"stable", "mastered"}
    assert curriculum["review_status"] in {"maintain", "soon", "due"}
    assert isinstance(curriculum["attention_reason"], str)
    assert curriculum["attention_reason"]

    skill_world = snapshot["skill_world"]
    assert skill_world["summary"]["map_progress_percent"] == 100
    assert skill_world["summary"]["completed_stage_count"] == len(bundle.curriculum.stage_order)
    assert all(node["status"] == "completed" for node in skill_world["nodes"])
    achievement_ids = {item["achievement_id"] for item in skill_world["achievements"]}
    assert "five_session_foundation" in achievement_ids
    assert "safe_three_session_streak" in achievement_ids
    assert "subskill_mastered:opening" in achievement_ids
