from __future__ import annotations

from runtime_context import DomainSessionContext, build_turn_id


REQUIRED_CONTEXT_FIELDS = (
    "skill_id",
    "capability_id",
    "action_id",
    "session_id",
    "turn_id",
    "learner_id",
    "scenario_id",
    "persona_id",
    "prompt_profile",
    "experiment_id",
    "locale",
    "trace_id",
)


def test_domain_session_context_serializes_core_fields() -> None:
    context = DomainSessionContext.from_session_seed(
        session_id="sess_001",
        learner_id="learner_001",
        scenario_id="scenario_001",
        persona_id="persona_001",
        prompt_context={
            "profile_id": "alpha_baseline_v1",
            "experiment_id": "exp_alpha",
            "flags": ["canary"],
        },
        continuity_context={"summary": "Keep the next opening concise."},
        trace_id="trace_001",
    ).for_action("send_turn", turn_id=build_turn_id("sess_001", 1))

    payload = context.to_dict()
    restored = DomainSessionContext.from_dict(payload)

    assert set(REQUIRED_CONTEXT_FIELDS).issubset(payload)
    assert payload["prompt_profile"] == "alpha_baseline_v1"
    assert payload["experiment_id"] == "exp_alpha"
    assert payload["trace_id"] == "trace_001"
    assert restored.to_dict() == payload


def test_domain_session_context_reaches_review_and_events() -> None:
    context = DomainSessionContext(
        skill_id="mr_visit_jp",
        capability_id="practice_session",
        action_id="finish_session",
        session_id="sess_001",
        turn_id="turn_003",
        learner_id="learner_001",
        scenario_id="scenario_001",
        persona_id="persona_001",
        prompt_profile="alpha_baseline_v1",
        experiment_id="exp_alpha",
        locale="ja-JP",
        trace_id="trace_001",
    )

    review_payload = {"metadata": {}}
    event_payload = {"metadata": {}}

    context.attach_to_review_metadata(review_payload["metadata"])
    context.attach_to_event_metadata(event_payload["metadata"])

    for field in ("session_id", "learner_id", "prompt_profile", "trace_id", "locale"):
        assert review_payload["metadata"][field] == getattr(context, field)
        assert event_payload["metadata"][field] == getattr(context, field)
    assert review_payload["metadata"]["continuity"]["summary"] == ""
    assert event_payload["metadata"]["continuity"]["carryover_focus_subskills"] == []
