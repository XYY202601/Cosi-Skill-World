from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

import main


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS_DIR = REPO_ROOT / "packages" / "shared-schemas" / "schemas"


def _load_schema(schema_name: str) -> dict:
    with (SCHEMAS_DIR / schema_name).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict)
    return payload


def _assert_schema(payload: object, schema_name: str) -> None:
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert not errors, errors[0].message


def test_runtime_api_responses_match_shared_schemas() -> None:
    with TestClient(main.app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        _assert_schema(health.json(), "runtime_health_response.schema.json")

        scenarios = client.get("/v1/scenarios")
        assert scenarios.status_code == 200
        scenarios_payload = scenarios.json()
        _assert_schema(scenarios_payload, "runtime_scenario_list_response.schema.json")

        gates = client.get("/v1/evaluation-gates")
        assert gates.status_code == 200
        _assert_schema(gates.json(), "runtime_evaluation_gates_response.schema.json")

        scenario_id = scenarios_payload["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_contract_001"},
        )
        assert started.status_code == 200
        started_payload = started.json()
        _assert_schema(started_payload, "runtime_session_start_response.schema.json")
        session_id = started_payload["session_id"]

        session = client.get(f"/v1/sessions/{session_id}")
        assert session.status_code == 200
        _assert_schema(session.json(), "runtime_session_response.schema.json")

        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "One concise evidence-backed point for a defined patient segment."},
        )
        assert turn.status_code == 200
        _assert_schema(turn.json(), "runtime_send_turn_response.schema.json")

        session_after_turn = client.get(f"/v1/sessions/{session_id}")
        assert session_after_turn.status_code == 200
        _assert_schema(session_after_turn.json(), "runtime_session_response.schema.json")

        events = client.get(f"/v1/sessions/{session_id}/events")
        assert events.status_code == 200
        events_payload = events.json()
        _assert_schema(events_payload, "runtime_session_events_response.schema.json")
        event_envelope_schema = _load_schema("session_event_envelope.schema.json")
        event_validator = Draft202012Validator(event_envelope_schema)
        for event in events_payload["events"]:
            errors = sorted(event_validator.iter_errors(event), key=lambda error: list(error.path))
            assert not errors, errors[0].message

        finished = client.post(f"/v1/sessions/{session_id}/finish")
        assert finished.status_code == 200
        _assert_schema(finished.json(), "runtime_finish_session_response.schema.json")

        feedback_create = client.post(
            "/_local/human-review-feedback/records",
            json={
                "session_id": session_id,
                "reviewer_id": "schema_sme_001",
                "reviewer_role": "sme",
                "verdict": "correct_ai_review",
                "subskill_score_overrides": {"opening": 2},
                "fixture_promotion": {
                    "include": True,
                    "bucket": "bad",
                    "name_hint": "schema_contract_feedback_case",
                    "tags": ["schema_contract"],
                },
            },
        )
        assert feedback_create.status_code == 200
        _assert_schema(
            feedback_create.json(),
            "runtime_human_review_feedback_record_response.schema.json",
        )

        feedback_list = client.get("/_local/human-review-feedback/records?latest_only=true")
        assert feedback_list.status_code == 200
        _assert_schema(
            feedback_list.json(),
            "runtime_human_review_feedback_record_list_response.schema.json",
        )

        feedback_export = client.get("/_local/human-review-feedback/export?latest_only=false")
        assert feedback_export.status_code == 200
        feedback_export_payload = feedback_export.json()
        _assert_schema(
            feedback_export_payload,
            "runtime_human_review_feedback_export_response.schema.json",
        )

        feedback_import = client.post(
            "/_local/human-review-feedback/import",
            json={"bundle": feedback_export_payload["bundle"]},
        )
        assert feedback_import.status_code == 200
        _assert_schema(
            feedback_import.json(),
            "runtime_human_review_feedback_import_response.schema.json",
        )

        feedback_candidates = client.get("/_local/human-review-feedback/fixture-candidates")
        assert feedback_candidates.status_code == 200
        _assert_schema(
            feedback_candidates.json(),
            "runtime_human_review_feedback_fixture_candidates_response.schema.json",
        )

        review = client.get(f"/v1/sessions/{session_id}/review")
        assert review.status_code == 200
        _assert_schema(review.json(), "runtime_review_response.schema.json")

        progress = client.get("/v1/learners/learner_contract_001/progress")
        assert progress.status_code == 200
        _assert_schema(progress.json(), "runtime_progress_snapshot_response.schema.json")

        organization_reports = client.get("/v1/organizations/local/reports")
        assert organization_reports.status_code == 200
        _assert_schema(
            organization_reports.json(),
            "runtime_organization_reports_response.schema.json",
        )
