from __future__ import annotations

from copy import deepcopy

from scenarios.asset_loader import ScenarioRecord, get_domain_bundle
from session_engine.state_machine import SessionEngine


def _continuity_for_scenario(
    scenario: ScenarioRecord,
    *,
    suggested_focus_subskills: list[str] | None = None,
    next_actions: list[str] | None = None,
    carryover_focus_subskills: list[str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "scenario_focus_subskills": list(scenario.focus_subskills),
        "suggested_focus_subskills": list(
            suggested_focus_subskills or scenario.focus_subskills
        ),
        "next_actions": list(next_actions or []),
        "success_criteria": list(scenario.success_criteria),
        "failure_patterns": list(scenario.failure_patterns),
    }
    if carryover_focus_subskills is not None:
        payload["carryover_focus_subskills"] = list(carryover_focus_subskills)
    return payload


def _neutral_persona(base_persona: dict[str, object]) -> dict[str, object]:
    persona = deepcopy(base_persona)
    persona["attitude"] = "neutral"
    persona["decision_style"] = "neutral"
    persona["time_pressure"] = "medium"
    return persona


def test_busy_persona_pushes_short_permission_based_opening() -> None:
    bundle = get_domain_bundle()
    scenario = bundle.scenarios["busy_doctor_short_visit"]
    persona = bundle.personas[scenario.doctor_persona_id]
    engine = SessionEngine()

    decision = engine._director_decide(
        turn_count=1,
        scenario=scenario,
        user_message=(
            "I want to tell you about our product and all the reasons it matters because the "
            "market is moving quickly and there are many details to cover right now."
        ),
        persona=persona,
        continuity_context=_continuity_for_scenario(
            scenario,
            suggested_focus_subskills=["opening"],
            next_actions=[
                "Ask permission, name the patient segment, and make one relevant point."
            ],
        ),
    )
    reply = engine._doctor_reply(
        turn_count=1,
        user_message=(
            "I want to tell you about our product and all the reasons it matters because the "
            "market is moving quickly and there are many details to cover right now."
        ),
        decision=decision,
        persona=persona,
        continuity_context=_continuity_for_scenario(
            scenario,
            suggested_focus_subskills=["opening"],
            next_actions=[
                "Ask permission, name the patient segment, and make one relevant point."
            ],
        ),
        scenario=scenario,
    )

    assert decision.phase == "opening"
    assert "opening_missing_permission" in decision.events
    assert "time_pressure_not_respected" in decision.events
    assert "patient_segment_not_specified" in decision.events
    assert decision.recommended_action == "shorten_opening_and_get_permission"
    assert "opening" in decision.taxonomy_categories
    assert "recovery" in decision.taxonomy_categories
    assert decision.turn_signals.has_permission is False
    assert decision.turn_signals.has_patient_segment is False
    assert "Ask permission" in reply
    assert "patient segment" in reply


def test_playbook_forces_safety_mode_even_with_neutral_persona() -> None:
    bundle = get_domain_bundle()
    scenario = bundle.scenarios["adverse_event_followup_required"]
    persona = _neutral_persona(bundle.personas[scenario.doctor_persona_id])
    engine = SessionEngine()

    decision = engine._director_decide(
        turn_count=1,
        scenario=scenario,
        user_message="I want to share a product update and why it matters for more patients.",
        persona=persona,
        continuity_context={},
    )

    assert decision.phase == "safety"
    assert "safety_first_context" in decision.events
    assert "safety_reporting_not_started" in decision.events
    assert decision.recommended_action == "state_reporting_process_and_followup"


def test_playbook_forces_formulary_discovery_even_with_neutral_persona() -> None:
    bundle = get_domain_bundle()
    scenario = bundle.scenarios["formulary_restriction_negotiation"]
    persona = _neutral_persona(bundle.personas[scenario.doctor_persona_id])
    engine = SessionEngine()

    decision = engine._director_decide(
        turn_count=1,
        scenario=scenario,
        user_message="The data is strong and we should talk about broader use.",
        persona=persona,
        continuity_context={},
    )
    reply = engine._doctor_reply(
        turn_count=1,
        user_message="The data is strong and we should talk about broader use.",
        decision=decision,
        persona=persona,
        continuity_context={},
        scenario=scenario,
    )

    assert "formulary_barrier_not_explored" in decision.events
    assert decision.recommended_action == "ask_about_formulary_barrier"
    assert scenario.playbook is not None
    assert scenario.playbook.key_discovery_questions[0] in reply


def test_playbook_forces_competitor_reframe_even_with_neutral_persona() -> None:
    bundle = get_domain_bundle()
    scenario = bundle.scenarios["skeptical_doctor_competitor_pressure"]
    persona = _neutral_persona(bundle.personas[scenario.doctor_persona_id])
    engine = SessionEngine()

    decision = engine._director_decide(
        turn_count=2,
        scenario=scenario,
        user_message="Our brand is better than the competitor and you should switch now.",
        persona=persona,
        continuity_context={},
    )
    reply = engine._doctor_reply(
        turn_count=2,
        user_message="Our brand is better than the competitor and you should switch now.",
        decision=decision,
        persona=persona,
        continuity_context={},
        scenario=scenario,
    )

    assert "decision_criteria_not_explored" in decision.events
    assert "unsupported_competitor_comparison" in decision.events
    assert decision.recommended_action == "ask_decision_criteria_before_comparison"
    assert scenario.playbook is not None
    assert scenario.playbook.key_discovery_questions[0] in reply


def test_evidence_reply_uses_playbook_acceptable_evidence_move() -> None:
    bundle = get_domain_bundle()
    scenario = bundle.scenarios["cautious_doctor_evidence_check"]
    persona = bundle.personas[scenario.doctor_persona_id]
    engine = SessionEngine()

    decision = engine._director_decide(
        turn_count=2,
        scenario=scenario,
        user_message="This has been working very well and should matter in practice.",
        persona=persona,
        continuity_context=_continuity_for_scenario(scenario),
    )
    reply = engine._doctor_reply(
        turn_count=2,
        user_message="This has been working very well and should matter in practice.",
        decision=decision,
        persona=persona,
        continuity_context=_continuity_for_scenario(scenario),
        scenario=scenario,
    )

    assert decision.phase == "evidence"
    assert "evidence_not_addressed" in decision.events
    assert decision.recommended_action == "cite_endpoint_safety_and_patient_segment"
    assert scenario.playbook is not None
    assert "subgroup analysis of Trial Z" in reply
    assert "endpoint" in reply.lower()
    assert "safety" in reply.lower()
    assert "patient segment" in reply.lower()


def test_low_interest_recovery_uses_playbook_discovery_question() -> None:
    bundle = get_domain_bundle()
    scenario = bundle.scenarios["low_interest_doctor_intro_fail"]
    persona = bundle.personas[scenario.doctor_persona_id]
    engine = SessionEngine()

    decision = engine._director_decide(
        turn_count=1,
        scenario=scenario,
        user_message="I have a general update to share with you today.",
        persona=persona,
        continuity_context={},
    )
    reply = engine._doctor_reply(
        turn_count=1,
        user_message="I have a general update to share with you today.",
        decision=decision,
        persona=persona,
        continuity_context={},
        scenario=scenario,
    )

    assert "weak_profiling_signal" in decision.events
    assert "discovery_question_missing" in decision.events
    assert decision.recommended_action == "ask_one_targeted_discovery_question"
    assert scenario.playbook is not None
    assert scenario.playbook.key_discovery_questions[0] in reply


def test_closing_reply_uses_playbook_completion_signal() -> None:
    bundle = get_domain_bundle()
    scenario = bundle.scenarios["busy_doctor_short_visit"]
    persona = bundle.personas[scenario.doctor_persona_id]
    engine = SessionEngine()
    continuity_context = _continuity_for_scenario(
        scenario,
        suggested_focus_subskills=["closing_followup"],
        carryover_focus_subskills=["closing_followup"],
    )

    decision = engine._director_decide(
        turn_count=7,
        scenario=scenario,
        user_message="The value is clear and we can keep discussing it.",
        persona=persona,
        continuity_context=continuity_context,
    )
    reply = engine._doctor_reply(
        turn_count=7,
        user_message="The value is clear and we can keep discussing it.",
        decision=decision,
        persona=persona,
        continuity_context=continuity_context,
        scenario=scenario,
    )

    assert decision.phase == "closing"
    assert "closing_next_step_missing" in decision.events
    assert "carryover_followup_gap" in decision.events
    assert decision.recommended_action == "state_micro_commitment_and_followup"
    assert scenario.playbook is not None
    assert scenario.playbook.completion_signals[0] in reply
    assert "follow-up timing" in reply.lower()


def test_max_turn_cutoff_is_labeled_as_completion() -> None:
    bundle = get_domain_bundle()
    scenario = bundle.scenarios["busy_doctor_short_visit"]
    persona = bundle.personas[scenario.doctor_persona_id]
    engine = SessionEngine()

    decision = engine._director_decide(
        turn_count=scenario.max_turns,
        scenario=scenario,
        user_message="The value is clear and we can keep discussing it.",
        persona=persona,
        continuity_context={},
    )

    assert decision.should_finish is True
    assert "max_turns_reached" in decision.events
    assert "completion" in decision.taxonomy_categories
