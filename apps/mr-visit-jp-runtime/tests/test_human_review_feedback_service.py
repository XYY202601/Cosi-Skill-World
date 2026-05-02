from __future__ import annotations

from pathlib import Path

from persistence.file_session_store import FileSessionStore
from scenarios.asset_loader import get_domain_bundle
from services.human_review_feedback import HumanReviewFeedbackService


def _finalized_session_payload(*, session_id: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "scenario_id": "busy_doctor_short_visit",
        "learner_id": "learner_feedback_001",
        "status": "finalized",
        "finish_reason": "manual_finish",
        "updated_at": "2026-04-29T00:00:00+00:00",
        "turns": [
            {
                "turn_index": 1,
                "user_message": "May I take one minute to align on your patient profile?",
                "doctor_reply": "Please keep it short.",
                "director_phase": "exploration",
                "director_events": ["opening_missing_permission"],
                "created_at": "2026-04-29T00:00:01Z",
            }
        ],
        "review": {
            "overall_score": 72,
            "overall_band": "functional",
            "priority_subskills": ["opening", "need_discovery"],
            "diagnosis": {"primary": [{"id": "weak_close_or_followup"}]},
            "compliance_flags": [],
            "meta": {"prompting": {"profile_id": "alpha_baseline_v1"}},
        },
    }


def test_human_review_feedback_service_appends_versioned_records(tmp_path: Path) -> None:
    session_store = FileSessionStore(tmp_path / "sessions")
    session_store.create(
        "sess_feedback_001",
        _finalized_session_payload(session_id="sess_feedback_001"),
    )
    service = HumanReviewFeedbackService(
        root_dir=tmp_path / "human_review_feedback",
        session_store=session_store,
        domain_bundle=get_domain_bundle(),
    )

    first = service.create_record(
        {
            "session_id": "sess_feedback_001",
            "reviewer_id": "sme_alice",
            "reviewer_role": "sme",
            "verdict": "correct_ai_review",
            "subskill_score_overrides": {"opening": 2},
            "diagnosis_add_ids": ["opening_not_permission_based"],
            "evidence_sufficiency": {"opening": False},
        }
    )
    assert first["version"] == 1

    second = service.create_record(
        {
            "session_id": "sess_feedback_001",
            "record_id": first["record_id"],
            "supersedes_version": 1,
            "reviewer_id": "sme_alice",
            "reviewer_role": "sme",
            "verdict": "correct_ai_review",
            "subskill_score_overrides": {"opening": 3},
            "sme_comment": "Add one more explicit permission sentence in opening.",
        }
    )
    assert second["version"] == 2
    assert second["supersedes_version"] == 1

    all_records = service.list_records()
    assert len(all_records) == 2
    latest_records = service.list_records(latest_only=True)
    assert len(latest_records) == 1
    assert latest_records[0]["version"] == 2


def test_human_review_feedback_service_exports_candidates_and_imports_bundle(
    tmp_path: Path,
) -> None:
    session_store = FileSessionStore(tmp_path / "sessions")
    session_store.create(
        "sess_feedback_002",
        _finalized_session_payload(session_id="sess_feedback_002"),
    )
    service = HumanReviewFeedbackService(
        root_dir=tmp_path / "human_review_feedback_a",
        session_store=session_store,
        domain_bundle=get_domain_bundle(),
    )
    imported_target = HumanReviewFeedbackService(
        root_dir=tmp_path / "human_review_feedback_b",
        session_store=session_store,
        domain_bundle=get_domain_bundle(),
    )

    record = service.create_record(
        {
            "session_id": "sess_feedback_002",
            "reviewer_id": "trainer_bob",
            "reviewer_role": "trainer",
            "verdict": "correct_ai_review",
            "subskill_score_overrides": {"need_discovery": 2},
            "fixture_promotion": {
                "include": True,
                "bucket": "continuity",
                "name_hint": "sme_carryover_gap_case",
                "scenario_ids": ["busy_doctor_short_visit"],
                "focus_subskills": ["need_discovery"],
                "tags": ["sme_feedback", "continuity_gap"],
            },
        }
    )
    assert record["fixture_promotion"]["include"] is True

    candidates = service.build_fixture_candidates()
    assert candidates["candidate_count"] == 1
    candidate = candidates["candidates"][0]
    assert candidate["ready"] is True
    assert candidate["fixture_path"] == "continuity/sme_carryover_gap_case.json"
    assert candidate["fixture"]["metadata"]["scenario_ids"] == ["busy_doctor_short_visit"]

    exported = service.export_bundle(latest_only=False)
    assert exported["record_count"] == 1

    imported_summary = imported_target.import_bundle(exported)
    assert imported_summary["imported_count"] == 1
    assert imported_summary["skipped_duplicate_count"] == 0
    duplicate_summary = imported_target.import_bundle(exported)
    assert duplicate_summary["imported_count"] == 0
    assert duplicate_summary["skipped_duplicate_count"] == 1
