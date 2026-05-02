from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from persistence.file_event_store import FileEventStore
from persistence.file_progress_store import FileProgressStore
from persistence.file_session_store import FileSessionStore
from scenarios.asset_loader import get_domain_bundle
from services.demo_progress_seed import (
    COMPREHENSIVE_TODAY_BATCH_GENERATOR,
    DEMO_SEED_GENERATOR,
    DemoLearnerSpec,
    append_comprehensive_today_sessions,
    ensure_demo_runtime_data,
)
from services.progress_tracker import ProgressTracker


def _sample_review(
    subskill_ids: list[str],
    *,
    overall_score: int = 72,
    priority_subskills: list[str] | None = None,
) -> dict[str, object]:
    priority_subskills = priority_subskills or ["opening", "scientific_delivery"]
    subskills: dict[str, dict[str, object]] = {}
    for subskill_id in subskill_ids:
        score = 2.0 if subskill_id in priority_subskills else 3.6
        subskills[subskill_id] = {"score": score, "evidence": ["fixture"]}

    return {
        "overall_score": overall_score,
        "priority_subskills": list(priority_subskills),
        "diagnosis": {
            "primary": [
                {
                    "id": "synthetic_gap",
                    "summary": "診断要約のサンプルです。",
                    "recommendation_focus": list(priority_subskills[:2]),
                    "related_subskills": list(priority_subskills[:2]),
                }
            ]
        },
        "coaching_feedback": {
            "version": 1,
            "focus_subskills": list(priority_subskills[:2]),
            "next_actions": ["許可を取ってから要点を短く伝える。"],
        },
        "compliance_flags": [],
        "subskills": subskills,
    }


def _contains_non_ascii(value: str) -> bool:
    return any(ord(char) > 127 for char in value)


def test_progress_tracker_preserves_extended_recent_history(tmp_path: Path) -> None:
    bundle = get_domain_bundle()
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        progress_store=FileProgressStore(tmp_path / "progress"),
    )
    scenario = bundle.scenarios["busy_doctor_short_visit"]
    persona = bundle.personas[scenario.doctor_persona_id]

    for index in range(25):
        tracker.apply_session_result(
            learner_id="learner_history_window",
            session_id=f"sess_window_{index:03d}",
            scenario_id=scenario.id,
            scenario_title=scenario.title,
            scenario_difficulty=scenario.difficulty,
            focus_subskills=list(scenario.focus_subskills),
            persona_id=scenario.doctor_persona_id,
            persona_label=str(persona["label"]),
            review=_sample_review(
                list(bundle.manifest["subskills"]),
                overall_score=60 + (index % 10),
                priority_subskills=["opening", "need_discovery"],
            ),
        )

    snapshot = tracker.get_snapshot("learner_history_window")
    assert snapshot["total_sessions"] == 25
    assert len(snapshot["recent_history"]) == 25
    assert snapshot["recent_history"][-1]["session_id"] == "sess_window_024"


def test_demo_seed_generates_japanese_progress_and_session_artifacts(tmp_path: Path) -> None:
    bundle = get_domain_bundle()
    progress_store = FileProgressStore(tmp_path / "progress")
    session_store = FileSessionStore(tmp_path / "sessions")
    event_store = FileEventStore(tmp_path / "events")
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        progress_store=progress_store,
    )

    ensure_demo_runtime_data(
        bundle=bundle,
        progress_tracker=tracker,
        progress_store=progress_store,
        session_store=session_store,
        event_store=event_store,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        specs=(
            DemoLearnerSpec(
                learner_id="learner_demo_unit",
                session_count=4,
                active_day_span=8,
                base_score=2.4,
                growth_bias=1.1,
                persistent_weaknesses=("need_discovery", "objection_handling"),
                strengths=("scientific_delivery",),
            ),
        ),
    )

    snapshot = tracker.get_snapshot("learner_demo_unit")
    assert snapshot["total_sessions"] == 4
    assert len(snapshot["recent_history"]) == 4
    assert all(isinstance(item.get("finish_reason"), str) and item.get("finish_reason") for item in snapshot["recent_history"])
    assert any(
        _contains_non_ascii(str(item.get("persona_label", "")))
        for item in snapshot["recent_history"]
    )
    assert any(
        _contains_non_ascii(str(item.get("scenario_title", "")))
        for item in snapshot["recent_history"]
    )
    assert any(
        "。" in str(summary)
        for item in snapshot["recent_history"]
        for summary in item.get("diagnosis_summaries", [])
    )

    latest_session_id = snapshot["recent_history"][-1]["session_id"]
    session_payload = session_store.get(latest_session_id)
    assert session_payload is not None
    assert session_payload["status"] == "finalized"
    assert session_payload["continuity_context"]["scenario_title_override"]
    assert session_payload["context"]["skill_id"] == "mr_visit_jp"
    assert session_payload["review"]["display_title"]
    assert session_payload["review"]["meta"]["generator"] == DEMO_SEED_GENERATOR

    events = event_store.list_events(latest_session_id)
    assert len(events) >= 3
    assert events[0]["type"] == "session_started"
    assert events[0]["content"]["taxonomy"]["categories"] == ["opening"]
    assert any(event["type"] == "turn_processed" for event in events)
    turn_event = next(event for event in events if event["type"] == "turn_processed")
    assert turn_event["content"]["signal_summary"]["token_count"] > 0
    assert turn_event["content"]["taxonomy"]["entries"]


def test_demo_seed_generates_diverse_japanese_histories(tmp_path: Path) -> None:
    bundle = get_domain_bundle()
    progress_store = FileProgressStore(tmp_path / "progress")
    session_store = FileSessionStore(tmp_path / "sessions")
    event_store = FileEventStore(tmp_path / "events")
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        progress_store=progress_store,
    )

    ensure_demo_runtime_data(
        bundle=bundle,
        progress_tracker=tracker,
        progress_store=progress_store,
        session_store=session_store,
        event_store=event_store,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        specs=(
            DemoLearnerSpec(
                learner_id="learner_demo_diverse",
                session_count=24,
                active_day_span=30,
                base_score=2.45,
                growth_bias=1.18,
                persistent_weaknesses=("opening", "need_discovery", "objection_handling"),
                strengths=("scientific_delivery",),
            ),
        ),
    )

    snapshot = tracker.get_snapshot("learner_demo_diverse")
    session_ids = [item["session_id"] for item in snapshot["recent_history"]]
    session_payloads = [session_store.get(session_id) for session_id in session_ids]
    session_payloads = [payload for payload in session_payloads if isinstance(payload, dict)]

    turn_counts = {int(payload["turn_count"]) for payload in session_payloads}
    finish_reasons = {str(payload["finish_reason"]) for payload in session_payloads}
    all_turns = [turn for payload in session_payloads for turn in payload.get("turns", [])]

    assert len(turn_counts) >= 2
    assert max(turn_counts) >= 5
    assert len(finish_reasons) >= 2
    assert any(reason in finish_reasons for reason in {"director_signaled_completion", "learner_requested_finish", "max_turns_reached"})
    assert all(_contains_non_ascii(str(turn.get("user_message", ""))) for turn in all_turns[:8])
    assert all(_contains_non_ascii(str(turn.get("doctor_reply", ""))) for turn in all_turns[:8])
    assert any("。" in str(turn.get("user_message", "")) for turn in all_turns)
    assert any(
        any(
            event["type"] == "session_finalized"
            and event["content"].get("finish_reason") == payload["finish_reason"]
            and event["content"]["taxonomy"]["categories"] == ["completion"]
            for event in event_store.list_events(str(payload["session_id"]))
        )
        for payload in session_payloads
    )


def test_demo_seed_refreshes_outdated_seed_version(tmp_path: Path) -> None:
    bundle = get_domain_bundle()
    progress_store = FileProgressStore(tmp_path / "progress")
    session_store = FileSessionStore(tmp_path / "sessions")
    event_store = FileEventStore(tmp_path / "events")

    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        progress_store=progress_store,
    )
    spec = DemoLearnerSpec(
        learner_id="learner_demo_refresh",
        session_count=3,
        active_day_span=7,
        base_score=2.4,
        growth_bias=1.1,
        persistent_weaknesses=("need_discovery", "objection_handling"),
        strengths=("scientific_delivery",),
    )

    ensure_demo_runtime_data(
        bundle=bundle,
        progress_tracker=tracker,
        progress_store=progress_store,
        session_store=session_store,
        event_store=event_store,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        specs=(spec,),
    )

    snapshot = tracker.get_snapshot(spec.learner_id)
    latest_session_id = snapshot["recent_history"][-1]["session_id"]
    latest_payload = session_store.get(latest_session_id)
    assert latest_payload is not None
    latest_payload["review"]["meta"]["generator"] = "demo_seed_v1"
    session_store.upsert(latest_session_id, latest_payload)

    refreshed_tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        progress_store=progress_store,
    )
    ensure_demo_runtime_data(
        bundle=bundle,
        progress_tracker=refreshed_tracker,
        progress_store=progress_store,
        session_store=session_store,
        event_store=event_store,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        specs=(spec,),
    )

    refreshed_payload = session_store.get(latest_session_id)
    assert refreshed_payload is not None
    assert refreshed_payload["review"]["meta"]["generator"] == DEMO_SEED_GENERATOR


def test_append_comprehensive_today_sessions_adds_25_same_day_diverse_records(
    tmp_path: Path,
) -> None:
    bundle = get_domain_bundle()
    progress_store = FileProgressStore(tmp_path / "progress")
    session_store = FileSessionStore(tmp_path / "sessions")
    event_store = FileEventStore(tmp_path / "events")
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        progress_store=progress_store,
    )

    created_session_ids = append_comprehensive_today_sessions(
        learner_id="learner_demo_today_batch",
        session_count=25,
        bundle=bundle,
        progress_tracker=tracker,
        session_store=session_store,
        event_store=event_store,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        anchor_now=datetime(2026, 4, 25, 18, 0, tzinfo=timezone(timedelta(hours=9))),
    )

    assert len(created_session_ids) == 25

    snapshot = tracker.get_snapshot("learner_demo_today_batch")
    assert snapshot["total_sessions"] == 25
    assert len(snapshot["recent_history"]) == 25

    session_payloads = [session_store.get(session_id) for session_id in created_session_ids]
    session_payloads = [payload for payload in session_payloads if isinstance(payload, dict)]
    assert len(session_payloads) == 25

    scenario_ids = {str(payload["scenario_id"]) for payload in session_payloads}
    finish_reasons = {str(payload["finish_reason"]) for payload in session_payloads}
    overall_bands = {str(payload["review"]["overall_band"]) for payload in session_payloads}
    compliance_rule_ids = {
        flag["rule_id"]
        for payload in session_payloads
        for flag in payload["review"].get("compliance_flags", [])
        if isinstance(flag, dict) and isinstance(flag.get("rule_id"), str)
    }
    started_dates = {
        datetime.fromisoformat(str(payload["started_at"])).date().isoformat()
        for payload in session_payloads
    }

    assert scenario_ids == set(bundle.scenarios.keys())
    assert finish_reasons == {
        "director_signaled_completion",
        "manual_finish",
        "learner_requested_finish",
        "max_turns_reached",
    }
    assert {"advanced", "proficient", "developing", "emerging"} <= overall_bands
    assert {
        "adverse_event_reporting_failure",
        "unsubstantiated_competitor_comparison",
        "fair_balance_omission",
        "off_label_or_unapproved_indication",
        "unsupported_outcome_promise",
    } <= compliance_rule_ids
    assert started_dates == {"2026-04-25"}
    assert all(
        payload["review"]["meta"]["generator"] == COMPREHENSIVE_TODAY_BATCH_GENERATOR
        for payload in session_payloads
    )


def test_append_comprehensive_today_sessions_appends_to_existing_learner_history(
    tmp_path: Path,
) -> None:
    bundle = get_domain_bundle()
    progress_store = FileProgressStore(tmp_path / "progress")
    session_store = FileSessionStore(tmp_path / "sessions")
    event_store = FileEventStore(tmp_path / "events")
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        progress_store=progress_store,
    )
    spec = DemoLearnerSpec(
        learner_id="learner_existing",
        session_count=2,
        active_day_span=2,
        base_score=2.4,
        growth_bias=1.0,
        persistent_weaknesses=("opening",),
        strengths=("scientific_delivery",),
    )

    ensure_demo_runtime_data(
        bundle=bundle,
        progress_tracker=tracker,
        progress_store=progress_store,
        session_store=session_store,
        event_store=event_store,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        specs=(spec,),
    )

    created_session_ids = append_comprehensive_today_sessions(
        learner_id="learner_existing",
        session_count=3,
        bundle=bundle,
        progress_tracker=tracker,
        session_store=session_store,
        event_store=event_store,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        anchor_now=datetime(2026, 4, 25, 18, 0, tzinfo=timezone(timedelta(hours=9))),
    )

    snapshot = tracker.get_snapshot("learner_existing")
    assert len(created_session_ids) == 3
    assert snapshot["total_sessions"] == 5
    assert len(snapshot["recent_history"]) == 5
    assert snapshot["recent_history"][-1]["session_id"] == created_session_ids[-1]


def test_append_comprehensive_today_sessions_supports_custom_turn_range(
    tmp_path: Path,
) -> None:
    bundle = get_domain_bundle()
    progress_store = FileProgressStore(tmp_path / "progress")
    session_store = FileSessionStore(tmp_path / "sessions")
    event_store = FileEventStore(tmp_path / "events")
    tracker = ProgressTracker(
        subskill_ids=list(bundle.manifest["subskills"]),
        scenario_catalog=bundle.scenarios,
        progress_store=progress_store,
    )

    created_session_ids = append_comprehensive_today_sessions(
        learner_id="learner_turn_window",
        session_count=10,
        min_turns=5,
        max_turns=10,
        bundle=bundle,
        progress_tracker=tracker,
        session_store=session_store,
        event_store=event_store,
        prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}},
        anchor_now=datetime(2026, 4, 25, 18, 0, tzinfo=timezone(timedelta(hours=9))),
    )

    assert len(created_session_ids) == 10
    payloads = [session_store.get(session_id) for session_id in created_session_ids]
    payloads = [payload for payload in payloads if isinstance(payload, dict)]
    assert len(payloads) == 10

    turn_counts = [int(payload["turn_count"]) for payload in payloads]
    assert min(turn_counts) >= 5
    assert max(turn_counts) <= 10
