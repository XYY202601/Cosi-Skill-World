from __future__ import annotations
import sys
from pathlib import Path

# Add evaluation-core to sys.path
repo_root = Path(__file__).resolve().parents[3]
eval_core_src = repo_root / "packages" / "evaluation-core" / "src"
if str(eval_core_src) not in sys.path:
    sys.path.insert(0, str(eval_core_src))

from evaluation_core.mr_visit_jp import ReviewBuildInputs, build_review_payload
from services.recommendation_engine import build_scenario_recommendations
from scenarios.asset_loader import get_domain_bundle

def test_continuity_scoring_logic():
    # Setup inputs with carryover subskills
    continuity_context = {
        "carryover_focus_subskills": ["opening", "profiling"]
    }
    
    # Simulate a review where learner failed "opening" but succeeded in "profiling"
    # Wait, build_review_payload calculates scores based on turns.
    # To test the scoring logic directly, I can look at the output of build_review_payload
    
    # We'll mock the features or just trust the logic I added to mr_visit_jp.py
    # Actually, let's test that the overall score is indeed adjusted.
    
    # Base Skill Score would be roughly:
    # opening (failed): 1-2
    # profiling (good): 4-5
    # others: 2-3
    
    # I'll use a mock turns list that triggers these
    turns = [
        {
            "turn_index": 1,
            "user_message": "Hello doctor. I want to talk about our product. It's very good and I have a lot of things to say and I will keep talking for a long time.", 
            "doctor_reply": "Go ahead.",
            "director_events": ["opening_missing_permission", "opening_overlong"]
        },
        {
            "turn_index": 2,
            "user_message": "What is the biggest barrier for your patients with hypertension?", # Question -> profiling success
            "doctor_reply": "Cost is a factor.",
            "director_events": []
        }
    ]
    
    bundle = get_domain_bundle()
    inputs = ReviewBuildInputs(
        turns=turns,
        turn_count=2,
        finish_reason="manual_finish",
        scenario_focus_subskills=["scientific_delivery"],
        subskill_weights={s: 1.0 for s in bundle.manifest.get("subskills", [])},
        skill_model=bundle.skill_model,
        diagnosis_types=bundle.diagnosis_types,
        compliance_rules=bundle.compliance_rules,
        score_schema={},
        judge_review_schema={},
        coach_feedback_schema={},
        compliance_flags_schema={},
        continuity_context=continuity_context
    )
    
    review = build_review_payload(inputs)
    
    # opening failed (carryover) -> -25 points
    # profiling succeeded (carryover) -> +5 points
    # base continuity: 100 - 25 + 5 = 80
    
    assert review["continuity_channel"]["score"] == 80
    assert "still requires significant focus" in str(review["continuity_channel"]["highlights"])
    assert "Successfully addressed" in str(review["continuity_channel"]["highlights"])

def test_continuity_recommendation_boost():
    bundle = get_domain_bundle()
    
    # Simulate review with failed carryover
    review = {
        "overall_score": 60,
        "subskills": {
            "opening": {"score": 2}, # FAILED CARRYOVER
            "profiling": {"score": 4}
        },
        "continuity_channel": {
            "carryover_subskills": ["opening"]
        }
    }
    
    recommendations = build_scenario_recommendations(
        scenarios=bundle.scenarios,
        current_scenario_id="scenario_a",
        current_scenario_difficulty="medium",
        review=review,
        recent_history=[],
        subskill_trends={},
        fallback_subskills=["opening"]
    )
    
    # Top recommendation should target "opening" and have type "continuity"
    top = recommendations[0]
    assert "opening" in top.target_subskills
    assert top.recommendation_type == "continuity"
    assert "carryover weakness" in top.reason.lower()


def test_partial_teaching_plan_achievement_keeps_continuity_priority():
    bundle = get_domain_bundle()

    review = {
        "overall_score": 66,
        "priority_subskills": ["opening"],
        "subskills": {
            "opening": {
                "score": 3,
                "evidence": [
                    {
                        "summary": "The learner still front-loaded the opening before asking permission.",
                        "turn_index": 1,
                    }
                ],
            }
        },
        "continuity_channel": {
            "carryover_subskills": ["opening"],
            "teaching_plan_achievement": {
                "status": "partially_achieved",
                "achieved_count": 0,
                "total_count": 1,
                "threshold": 4.0,
            },
        },
    }

    recommendations = build_scenario_recommendations(
        scenarios=bundle.scenarios,
        current_scenario_id="busy_doctor_short_visit",
        current_scenario_difficulty="easy",
        review=review,
        recent_history=[
            {
                "session_id": "sess_continuity_partial",
                "scenario_id": "busy_doctor_short_visit",
                "weak_subskills": ["opening"],
                "teaching_plan_achievement": {
                    "status": "partially_achieved",
                    "achieved_count": 0,
                    "total_count": 1,
                    "threshold": 4.0,
                },
            }
        ],
        subskill_trends={},
        fallback_subskills=["opening"],
        frozen_teaching_plan={
            "focus_subskills": ["opening"],
            "reason": "Carry forward the opening target.",
            "target_behavior": "Ask permission before expanding the opening.",
            "success_criterion": "Reach 4.0+ in opening.",
            "score_threshold": 4.0,
        },
    )

    top = recommendations[0]
    assert "opening" in top.target_subskills
    assert top.recommendation_type == "continuity"
    assert top.reason_category in {"continuity", "mixed"}
    assert "frozen teaching-plan target" in top.reason.lower()
    assert "partially achieved" in str(top.evidence_source).lower()
