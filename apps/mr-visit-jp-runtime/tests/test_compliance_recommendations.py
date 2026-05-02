from __future__ import annotations

import pytest
from scenarios.asset_loader import get_domain_bundle
from services.recommendation_engine import build_scenario_recommendations

def test_compliance_risk_triggers_remedial_recommendation():
    bundle = get_domain_bundle()
    
    # Simulate a review with a critical compliance risk in a HARD scenario
    review = {
        "overall_score": 40,
        "compliance_flags": [
            {
                "rule_id": "adverse_event_reporting_failure",
                "severity": "critical",
                "tag": "compliance_risk"
            }
        ],
        "priority_subskills": ["closing_followup", "profiling"]
    }
    
    recent_history = [
        {
            "scenario_id": "adverse_event_followup_required",
            "weak_subskills": ["closing_followup", "profiling"]
        }
    ]
    
    recommendations = build_scenario_recommendations(
        scenarios=bundle.scenarios,
        current_scenario_id="adverse_event_followup_required",
        current_scenario_difficulty="hard",
        review=review,
        recent_history=recent_history,
        subskill_trends={},
        fallback_subskills=["scientific_delivery"]
    )
    
    # Verify that the top recommendation addresses the compliance risk
    # It should pick something with overlap but lower difficulty if available.
    # Actually, let's just check that it picks a compliance type recommendation if there's overlap.
    top = recommendations[0]
    assert top.recommendation_type == "compliance"
    # Since current was hard, target is medium. 
    # 'busy_doctor_short_visit' has overlap [closing_followup] and difficulty easy.
    # 'new_product_adoption_barrier' has overlap [profiling] and difficulty medium.
    
    # If it picks 'new_product_adoption_barrier', it steps down from hard to medium.
    if top.scenario_id == "new_product_adoption_barrier":
        assert "steps difficulty down" in top.reason.lower()

def test_positive_compliance_no_remedial():
    bundle = get_domain_bundle()
    
    # Simulate a review with positive compliance
    review = {
        "overall_score": 85,
        "compliance_flags": [
            {
                "rule_id": "correct_ae_handling",
                "severity": "positive",
                "tag": "safe_ae_reporting"
            }
        ],
        "priority_subskills": ["scientific_delivery"]
    }
    
    recent_history = []
    
    recommendations = build_scenario_recommendations(
        scenarios=bundle.scenarios,
        current_scenario_id="adverse_event_followup_required",
        current_scenario_difficulty="hard",
        review=review,
        recent_history=recent_history,
        subskill_trends={},
        fallback_subskills=["scientific_delivery"]
    )
    
    # Should not trigger compliance remedial path
    top = recommendations[0]
    assert top.recommendation_type == "skill"
