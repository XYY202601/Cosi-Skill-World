from __future__ import annotations
from evaluation_core.mr_visit_jp import ReviewBuildInputs, build_review_payload

def test_timeline_generation():
    turns = [
        {
            "turn_index": 1,
            "user_message": "Hello",
            "director_phase": "opening",
            "director_events": ["opening_missing_permission"]
        },
        {
            "turn_index": 2,
            "user_message": "Can I ask a question?",
            "director_phase": "profiling",
            "director_events": []
        }
    ]
    
    inputs = ReviewBuildInputs(
        turns=turns,
        turn_count=2,
        finish_reason="manual_finish",
        scenario_focus_subskills=[],
        subskill_weights={"opening": 1.0, "profiling": 1.0, "preparation": 1.0, "scientific_delivery": 1.0, "need_discovery": 1.0, "objection_handling": 1.0, "closing_followup": 1.0},
        skill_model={"bands": [{"id": "excellent", "min": 90, "max": 100}, {"id": "strong", "min": 75, "max": 89}, {"id": "functional", "min": 60, "max": 74}, {"id": "emerging", "min": 40, "max": 59}, {"id": "critical_gap", "min": 0, "max": 39}]},
        diagnosis_types={"primary": []},
        compliance_rules={"rules": []},
        score_schema={},
        judge_review_schema={},
        coach_feedback_schema={},
        compliance_flags_schema={},
    )
    
    review = build_review_payload(inputs)
    
    assert "timeline" in review
    assert len(review["timeline"]) == 2
    
    # Turn 1: opening_missing_permission -> poor
    assert review["timeline"][0]["rating"] == "poor"
    assert "Requires focus" in review["timeline"][0]["comment"]
    
    # Turn 2: No events -> excellent
    assert review["timeline"][1]["rating"] == "excellent"
    assert "Solid performance" in review["timeline"][1]["comment"]
