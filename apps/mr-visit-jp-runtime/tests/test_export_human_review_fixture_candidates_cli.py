from __future__ import annotations

import json
from pathlib import Path

from export_human_review_fixture_candidates import run
from persistence.file_session_store import FileSessionStore
from scenarios.asset_loader import get_domain_bundle
from services.human_review_feedback import HumanReviewFeedbackService


def _finalized_session_payload(*, session_id: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "scenario_id": "busy_doctor_short_visit",
        "learner_id": "learner_cli_001",
        "status": "finalized",
        "finish_reason": "manual_finish",
        "updated_at": "2026-04-29T00:00:00+00:00",
        "turns": [
            {
                "turn_index": 1,
                "user_message": "May I align on one patient profile before data sharing?",
                "doctor_reply": "Sure, one minute.",
                "director_phase": "exploration",
                "director_events": ["opening_missing_permission"],
                "created_at": "2026-04-29T00:00:01Z",
            }
        ],
        "review": {
            "overall_score": 74,
            "overall_band": "functional",
            "priority_subskills": ["opening"],
            "diagnosis": {"primary": [{"id": "opening_not_permission_based"}]},
            "compliance_flags": [],
            "meta": {"prompting": {"profile_id": "alpha_baseline_v1"}},
        },
    }


def test_export_human_review_fixture_candidates_cli_apply_writes_fixture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "runtime-data"
    output_dir = tmp_path / "fixtures"
    monkeypatch.setenv("MR_RUNTIME_PERSISTENCE_MODE", "file")
    session_store = FileSessionStore(data_dir / "sessions")
    session_store.create(
        "sess_cli_001",
        _finalized_session_payload(session_id="sess_cli_001"),
    )
    feedback_service = HumanReviewFeedbackService(
        root_dir=data_dir / "human_review_feedback",
        session_store=session_store,
        domain_bundle=get_domain_bundle(),
    )
    feedback_service.create_record(
        {
            "session_id": "sess_cli_001",
            "reviewer_id": "trainer_cli",
            "reviewer_role": "trainer",
            "verdict": "correct_ai_review",
            "fixture_promotion": {
                "include": True,
                "bucket": "good",
                "name_hint": "cli_export_feedback_fixture",
                "tags": ["cli_export"],
            },
        }
    )

    exit_code = run(
        [
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(output_dir),
            "--apply",
        ]
    )
    assert exit_code == 0

    fixture_path = output_dir / "good" / "cli_export_feedback_fixture.json"
    assert fixture_path.exists()
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert payload["name"] == "cli_export_feedback_fixture"
    assert payload["metadata"]["tags"] == ["cli_export"]


def test_export_human_review_fixture_candidates_cli_dry_run_does_not_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "runtime-data"
    output_dir = tmp_path / "fixtures"
    monkeypatch.setenv("MR_RUNTIME_PERSISTENCE_MODE", "file")
    session_store = FileSessionStore(data_dir / "sessions")
    session_store.create(
        "sess_cli_002",
        _finalized_session_payload(session_id="sess_cli_002"),
    )
    feedback_service = HumanReviewFeedbackService(
        root_dir=data_dir / "human_review_feedback",
        session_store=session_store,
        domain_bundle=get_domain_bundle(),
    )
    feedback_service.create_record(
        {
            "session_id": "sess_cli_002",
            "reviewer_id": "trainer_cli",
            "reviewer_role": "trainer",
            "verdict": "correct_ai_review",
            "fixture_promotion": {
                "include": True,
                "bucket": "medium",
                "name_hint": "cli_export_dry_run_fixture",
                "tags": ["cli_dry_run"],
            },
        }
    )

    exit_code = run(
        [
            "--data-dir",
            str(data_dir),
            "--output-dir",
            str(output_dir),
        ]
    )
    assert exit_code == 0
    assert not (output_dir / "medium" / "cli_export_dry_run_fixture.json").exists()
