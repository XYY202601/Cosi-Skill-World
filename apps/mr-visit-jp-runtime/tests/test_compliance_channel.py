from __future__ import annotations

import pytest
from evaluation.review_builder import build_runtime_review
from scenarios.asset_loader import get_domain_bundle

def test_compliance_channel_detailed_output():
    turns = [
        {
            "turn_index": 1,
            "user_message": "This drug is 100% guaranteed to cure everyone.",
            "doctor_reply": "",
            "director_phase": "exploration",
            "director_events": [],
            "created_at": "2026-01-01T00:00:01Z",
        },
        {
            "turn_index": 2,
            "user_message": "Also, our competitor's product is much worse and dangerous.",
            "doctor_reply": "",
            "director_phase": "exploration",
            "director_events": [],
            "created_at": "2026-01-01T00:00:02Z",
        }
    ]

    bundle = get_domain_bundle()
    subskill_weights = {
        subskill_id: float(payload["weight"])
        for subskill_id, payload in bundle.skill_model["subskills"].items()
    }

    review = build_runtime_review(
        turns=turns,
        turn_count=len(turns),
        finish_reason="manual_finish",
        scenario_focus_subskills=["scientific_delivery", "objection_handling"],
        subskill_weights=subskill_weights,
        skill_model=bundle.skill_model,
        diagnosis_types=bundle.diagnosis_types,
        compliance_rules=bundle.compliance_rules,
        score_schema=bundle.score_schema,
        judge_review_schema=bundle.judge_review_schema,
        coach_feedback_schema=bundle.coach_feedback_schema,
        compliance_flags_schema=bundle.compliance_flags_schema,
        model_artifacts=None,
        model_error=None,
    )

    # Check Compliance Channel
    assert "compliance_channel" in review
    channel = review["compliance_channel"]
    assert channel["overall_status"] == "at_risk"
    assert channel["remedial_required"] is True
    
    flags = channel["flags"]
    assert len(flags) >= 2
    
    promise_flag = next(f for f in flags if f["rule_id"] == "unsupported_outcome_promise")
    assert promise_flag["severity"] == "high"
    assert promise_flag["remedial_priority"] == 70
    assert len(promise_flag["evidence"]) > 0
    assert promise_flag["evidence"][0]["turn_index"] == 1
    assert "100%" in promise_flag["evidence"][0]["excerpt"]
    assert "required_handling" in promise_flag

    competitor_flag = next(f for f in flags if f["rule_id"] == "unsubstantiated_competitor_comparison")
    assert competitor_flag["severity"] == "high"
    assert len(competitor_flag["evidence"]) > 0
    assert competitor_flag["evidence"][0]["turn_index"] == 2

def test_positive_compliance_ae_handling():
    turns = [
        {
            "turn_index": 1,
            "user_message": "I understand there was an adverse event. I will report this according to our SOP.",
            "doctor_reply": "",
            "director_phase": "exploration",
            "director_events": [],
            "created_at": "2026-01-01T00:00:01Z",
        }
    ]

    bundle = get_domain_bundle()
    subskill_weights = {
        subskill_id: float(payload["weight"])
        for subskill_id, payload in bundle.skill_model["subskills"].items()
    }

    review = build_runtime_review(
        turns=turns,
        turn_count=len(turns),
        finish_reason="manual_finish",
        scenario_focus_subskills=["profiling", "closing_followup"],
        subskill_weights=subskill_weights,
        skill_model=bundle.skill_model,
        diagnosis_types=bundle.diagnosis_types,
        compliance_rules=bundle.compliance_rules,
        score_schema=bundle.score_schema,
        judge_review_schema=bundle.judge_review_schema,
        coach_feedback_schema=bundle.coach_feedback_schema,
        compliance_flags_schema=bundle.compliance_flags_schema,
        model_artifacts=None,
        model_error=None,
    )

    channel = review["compliance_channel"]
    flags = channel["flags"]
    
    positive_flag = next(f for f in flags if f["rule_id"] == "correct_ae_handling")
    assert positive_flag["severity"] == "positive"
    assert positive_flag["remedial_priority"] == 0
    assert len(positive_flag["evidence"]) > 0
    assert positive_flag["evidence"][0]["turn_index"] == 1
