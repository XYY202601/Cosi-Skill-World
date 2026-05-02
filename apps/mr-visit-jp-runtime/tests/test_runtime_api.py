from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from providers import PromptAssetError, clear_prompt_asset_cache
from providers.model_artifact_generator import ModelArtifactGenerationError
from scenarios.asset_loader import get_domain_bundle


@pytest.fixture(autouse=True)
def clear_bundle_cache():
    get_domain_bundle.cache_clear()
    clear_prompt_asset_cache()
    yield
    get_domain_bundle.cache_clear()
    clear_prompt_asset_cache()


@pytest.fixture(autouse=True)
def isolate_runtime_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runtime_data = tmp_path / "runtime-data"
    monkeypatch.setenv("MR_RUNTIME_DATA_DIR", str(runtime_data))
    monkeypatch.setenv("MR_RUNTIME_MODEL_MODE", "mock")
    monkeypatch.setenv("MR_RUNTIME_DEMO_SEED_MODE", "manual")
    monkeypatch.delenv("MR_RUNTIME_DISABLE_DEMO_SEED", raising=False)
    yield runtime_data


def _assert_recommendation_shape(
    recommendation: dict[str, object],
    *,
    step_index: int | None = None,
) -> None:
    assert recommendation["expected_difficulty"] in {"easy", "medium", "hard", None}
    assert isinstance(recommendation["reason_category"], str)
    assert recommendation["reason_category"] in {
        "skill",
        "compliance",
        "continuity",
        "mixed",
        "curriculum",
    }
    assert isinstance(recommendation["suggested_repetition_count"], int)
    assert recommendation["suggested_repetition_count"] >= 1
    if step_index is not None:
        assert recommendation["step_index"] == step_index


def _assert_teaching_plan_snapshot(
    coach_continuity: dict[str, object],
    *,
    session_id: str,
    frozen_at: str | None = None,
    source_session_id: str | None = None,
) -> dict[str, object]:
    teaching_plan = coach_continuity["teaching_plan"]
    assert isinstance(teaching_plan, dict)
    assert teaching_plan["version"] == 1

    snapshot = coach_continuity["teaching_plan_snapshot"]
    assert isinstance(snapshot, dict)
    assert snapshot["snapshot_id"] == f"tp_{session_id}"
    assert snapshot["plan_version"] == teaching_plan["version"]
    if frozen_at is not None:
        assert snapshot["frozen_at"] == frozen_at
    else:
        assert isinstance(snapshot["frozen_at"], str)
        assert snapshot["frozen_at"]
    if source_session_id is not None:
        assert snapshot["source_session_id"] == source_session_id
    return snapshot


def _start_and_finish_session(
    client: TestClient,
    *,
    scenario_id: str,
    learner_id: str,
    headers: dict[str, str] | None = None,
    message: str = "One concise, evidence-backed point tied to a clear patient segment.",
) -> dict[str, object]:
    started = client.post(
        "/v1/sessions/start",
        json={"scenario_id": scenario_id, "learner_id": learner_id},
        headers=headers,
    )
    assert started.status_code == 200, started.json()
    session_id = started.json()["session_id"]

    turn = client.post(
        f"/v1/sessions/{session_id}/turn",
        json={"message": message},
        headers=headers,
    )
    assert turn.status_code == 200, turn.json()

    finished = client.post(
        f"/v1/sessions/{session_id}/finish",
        headers=headers,
    )
    assert finished.status_code == 200, finished.json()
    return finished.json()


def test_startup_fails_when_domain_assets_are_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom():
        raise main.DomainAssetError("invalid domain assets")

    monkeypatch.setattr(main, "get_domain_bundle", _boom)
    with pytest.raises(main.DomainAssetError, match="invalid domain assets"):
        with TestClient(main.app):
            pass


def test_startup_fails_when_prompt_assets_are_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom():
        raise PromptAssetError("invalid prompt assets")

    monkeypatch.setattr(main, "load_prompt_asset_bundle", _boom)
    with pytest.raises(PromptAssetError, match="invalid prompt assets"):
        with TestClient(main.app):
            pass


@pytest.mark.parametrize("seed_mode", ["manual", "disabled"])
def test_startup_seed_modes_skip_demo_seed(
    monkeypatch: pytest.MonkeyPatch,
    seed_mode: str,
) -> None:
    calls: list[dict[str, object]] = []

    def _fake_seed(**kwargs):
        calls.append(kwargs)

    monkeypatch.setenv("MR_RUNTIME_DEMO_SEED_MODE", seed_mode)
    monkeypatch.delenv("MR_RUNTIME_DISABLE_DEMO_SEED", raising=False)
    monkeypatch.setattr(main, "ensure_demo_runtime_data", _fake_seed)

    with TestClient(main.app):
        pass

    assert calls == []


def test_startup_auto_seed_mode_runs_demo_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def _fake_seed(**kwargs):
        calls.append(kwargs)

    monkeypatch.setenv("MR_RUNTIME_DEMO_SEED_MODE", "auto")
    monkeypatch.delenv("MR_RUNTIME_DISABLE_DEMO_SEED", raising=False)
    monkeypatch.setattr(main, "ensure_demo_runtime_data", _fake_seed)

    with TestClient(main.app):
        pass

    assert len(calls) == 1
    assert "bundle" in calls[0]
    assert "progress_tracker" in calls[0]
    assert "prompt_context" in calls[0]


def test_runtime_trace_headers_and_logs_preserve_safe_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="mr_visit_jp_runtime.observability")

    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            headers={
                "x-request-id": "req_runtime_001",
                "x-trace-id": "trace_runtime_001",
            },
            json={"scenario_id": scenario_id, "learner_id": "learner_runtime_safe_log"},
        )
        assert started.status_code == 200
        session_id = started.json()["session_id"]
        assert started.headers["x-request-id"] == "req_runtime_001"
        assert started.headers["x-trace-id"] == "trace_runtime_001"
        assert started.headers["x-session-id"] == session_id
        assert started.headers["x-service-name"] == "mr-visit-jp-runtime"

        sensitive_turn_message = "PRIVATE turn body should never be logged."
        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            headers={
                "x-request-id": "req_runtime_002",
                "x-trace-id": "trace_runtime_ignored",
            },
            json={"message": sensitive_turn_message},
        )
        assert turn.status_code == 200
        assert turn.headers["x-request-id"] == "req_runtime_002"
        assert turn.headers["x-trace-id"] == "trace_runtime_001"
        assert turn.headers["x-session-id"] == session_id
        assert turn.headers["x-turn-id"] == f"{session_id}:turn:0001"

    log_messages = [record.message for record in caplog.records]
    assert any('"request_id": "req_runtime_001"' in message for message in log_messages)
    assert any(f'"session_id": "{session_id}"' in message for message in log_messages)
    assert any('"trace_id": "trace_runtime_001"' in message for message in log_messages)
    assert any('"learner_hash":' in message for message in log_messages)
    assert all("learner_runtime_safe_log" not in message for message in log_messages)
    assert all(sensitive_turn_message not in message for message in log_messages)


def test_runtime_local_diagnostics_report_recent_session_context() -> None:
    with TestClient(main.app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        health_payload = health.json()
        assert health_payload["persistence_mode"] in ("file", "sql")
        assert health_payload["prompt_profile"] == "alpha_baseline_v1"

        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_diag_001"},
        )
        assert started.status_code == 200
        session_id = started.json()["session_id"]

        diagnostics = client.get("/_local/diagnostics")
        assert diagnostics.status_code == 200
        payload = diagnostics.json()
        assert payload["service_name"] == "mr-visit-jp-runtime"
        assert payload["domain_id"] == "mr_visit_jp"
        assert payload["persistence_mode"] in ("file", "sql")
        assert payload["prompt_context"]["profile_id"] == "alpha_baseline_v1"
        assert payload["session_counts"]["total"] >= 1
        recent_session = next(
            item for item in payload["recent_sessions"] if item["session_id"] == session_id
        )
        assert recent_session["learner_id"] == "learner_diag_001"
        assert recent_session["learner_hash"]
        assert recent_session["prompt_profile"] == "alpha_baseline_v1"
        assert recent_session["trace_id"] == started.headers["x-trace-id"]


def test_local_human_review_feedback_end_to_end() -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        finished = _start_and_finish_session(
            client,
            scenario_id=scenario_id,
            learner_id="learner_h4_feedback_001",
        )
        session_id = str(finished["session_id"])

        created = client.post(
            "/_local/human-review-feedback/records",
            json={
                "session_id": session_id,
                "reviewer_id": "sme_h4_001",
                "reviewer_role": "sme",
                "verdict": "correct_ai_review",
                "subskill_score_overrides": {"opening": 2},
                "diagnosis_add_ids": ["opening_not_permission_based"],
                "evidence_sufficiency": {"opening": False},
                "fixture_promotion": {
                    "include": True,
                    "bucket": "bad",
                    "name_hint": "h4_local_feedback_candidate",
                    "tags": ["h4", "sme_feedback"],
                },
            },
        )
        assert created.status_code == 200, created.json()
        created_record = created.json()["record"]
        assert created_record["version"] == 1
        assert created_record["session_id"] == session_id

        listed = client.get("/_local/human-review-feedback/records?latest_only=true")
        assert listed.status_code == 200, listed.json()
        assert listed.json()["record_count"] == 1
        assert listed.json()["records"][0]["record_id"] == created_record["record_id"]

        exported = client.get("/_local/human-review-feedback/export?latest_only=false")
        assert exported.status_code == 200, exported.json()
        export_bundle = exported.json()["bundle"]
        assert export_bundle["record_count"] == 1
        assert export_bundle["records"][0]["record_id"] == created_record["record_id"]

        candidates = client.get("/_local/human-review-feedback/fixture-candidates")
        assert candidates.status_code == 200, candidates.json()
        candidate_payload = candidates.json()["payload"]
        assert candidate_payload["candidate_count"] == 1
        first_candidate = candidate_payload["candidates"][0]
        assert first_candidate["ready"] is True
        assert first_candidate["fixture_path"] == "bad/h4_local_feedback_candidate.json"

        imported = client.post(
            "/_local/human-review-feedback/import",
            json={"bundle": export_bundle},
        )
        assert imported.status_code == 200, imported.json()
        import_summary = imported.json()["summary"]
        assert import_summary["imported_count"] == 0
        assert import_summary["skipped_duplicate_count"] == 1


def test_start_session_unknown_scenario_returns_404() -> None:
    with TestClient(main.app) as client:
        response = client.post(
            "/v1/sessions/start",
            json={"scenario_id": "does_not_exist", "learner_id": "learner_001"},
        )
    assert response.status_code == 404
    assert "Unknown scenario_id" in response.json()["detail"]


@pytest.mark.skipif(
    os.environ.get("MR_RUNTIME_PERSISTENCE_MODE") == "sql",
    reason="file-persistence specific (reads filesystem paths directly)",
)
def test_runtime_startup_skips_corrupted_unrelated_session_payload(
    isolate_runtime_data_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken_path = isolate_runtime_data_dir / "sessions" / "sess_corrupted_startup.json"
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_text('{"session_id": "sess_corrupted_startup",', encoding="utf-8")
    caplog.set_level(logging.WARNING, logger="mr_visit_jp_runtime.persistence")

    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios")
        assert scenarios.status_code == 200
        scenario_id = scenarios.json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_safe_after_corruption"},
        )
        assert started.status_code == 200

    warning_messages = [record.message for record in caplog.records]
    assert any("sess_corrupted_startup" in message for message in warning_messages)
    assert any(str(broken_path) in message for message in warning_messages)


def test_get_review_unknown_session_returns_404() -> None:
    with TestClient(main.app) as client:
        response = client.get("/v1/sessions/sess_missing/review")
    assert response.status_code == 404
    assert "Unknown session_id" in response.json()["detail"]


def test_get_progress_snapshot_unknown_learner_returns_404() -> None:
    with TestClient(main.app) as client:
        response = client.get("/v1/learners/learner_missing/progress")
    assert response.status_code == 404
    assert "No progress snapshot" in response.json()["detail"]


def test_get_session_events_unknown_session_returns_404() -> None:
    with TestClient(main.app) as client:
        response = client.get("/v1/sessions/sess_missing/events")
    assert response.status_code == 404
    assert "Unknown session_id" in response.json()["detail"]


def test_get_evaluation_gates_returns_offline_and_online_status() -> None:
    with TestClient(main.app) as client:
        response = client.get("/v1/evaluation-gates")
        assert response.status_code == 200
        payload = response.json()
        assert payload["domain_id"] == "mr_visit_jp"
        assert payload["default_profile_id"] == "alpha_baseline_v1"
        assert payload["rollout"]["status"] == "active"
        assert payload["rollout"]["requested"]["profile_id"] == "alpha_baseline_v1"
        assert payload["rollout"]["effective"]["profile_id"] == "alpha_baseline_v1"
        assert payload["offline_dataset"]["fixture_count"] >= 10
        assert payload["offline_dataset"]["coverage"]["scenarios"]["missing"] == []
        assert len(payload["offline_gates"]) >= 2
        assert any(item["profile_id"] == "alpha_coach_concise_v1" for item in payload["offline_gates"])
        assert payload["offline_gates"][0]["fixture_results"][0]["fixture_path"]
        assert len(payload["online_gates"]) >= 1
        assert payload["online_gates"][0]["status"] in ("insufficient_data", "pass", "fail")


def test_get_review_before_finish_returns_409() -> None:
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios")
        scenario_id = scenarios.json()["scenarios"][0]["id"]

        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_001"},
        )
        session_id = started.json()["session_id"]

        client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "I have one key update with evidence for your patient segment."},
        )
        response = client.get(f"/v1/sessions/{session_id}/review")
    assert response.status_code == 409
    assert "Finish the session first" in response.json()["detail"]


def test_finish_before_first_turn_returns_409() -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_finish_guard"},
        )
        session_id = started.json()["session_id"]

        response = client.post(f"/v1/sessions/{session_id}/finish")
    assert response.status_code == 409
    assert "Cannot finish session before first turn" in response.json()["detail"]


def test_session_state_machine_skeleton_flow() -> None:
    learner_id = f"test_learner_{uuid.uuid4().hex[:8]}"
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios")
        assert scenarios.status_code == 200
        scenario_id = scenarios.json()["scenarios"][0]["id"]

        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": learner_id},
        )
        assert started.status_code == 200
        started_payload = started.json()
        session_id = started_payload["session_id"]
        assert started_payload["experiment_context"]["profile_id"] == "alpha_baseline_v1"
        assert started_payload["experiment_context"]["contracts"]["coach"]["version"] == 1
        assert started_payload["scenario"]["persona_label"]
        assert "summary" in started_payload["coach_continuity"]
        assert started_payload["coach_continuity"]["teaching_plan"] is None
        assert started_payload["coach_continuity"]["teaching_plan_snapshot"] is None

        session_state = client.get(f"/v1/sessions/{session_id}")
        assert session_state.status_code == 200
        session_state_payload = session_state.json()
        assert session_state_payload["scenario"]["id"] == scenario_id
        assert session_state_payload["coach_continuity"]["suggested_focus_subskills"]
        assert session_state_payload["coach_continuity"]["teaching_plan"] is None
        assert session_state_payload["coach_continuity"]["teaching_plan_snapshot"] is None
        assert session_state_payload["turns"] == []

        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "I have one key update with evidence for your patient segment."},
        )
        assert turn.status_code == 200
        assert turn.json()["status"] in {"running", "awaiting_finish"}

        finished = client.post(f"/v1/sessions/{session_id}/finish")
        assert finished.status_code == 200
        payload = finished.json()
        assert payload["status"] == "finalized"
        assert "review" in payload
        assert "overall_score" in payload["review"]
        assert payload["review"]["meta"]["evaluation_mode"] == "evaluation_core_v1"
        assert payload["review"]["meta"]["artifact_sources"]["judge"] in {"model", "rule"}
        assert payload["review"]["meta"]["prompting"]["profile_id"] == "alpha_baseline_v1"
        assert payload["review"]["meta"]["prompting"]["contracts"]["judge"]["version"] == 1
        assert payload["review"]["meta"]["context"]["skill_id"] == "mr_visit_jp"
        assert payload["review"]["meta"]["context"]["session_id"] == session_id
        assert payload["review"]["meta"]["context"]["learner_id"] == learner_id
        assert payload["review"]["meta"]["context"]["prompt_profile"] == "alpha_baseline_v1"
        assert payload["review"]["meta"]["context"]["trace_id"].startswith("trace_")
        assert isinstance(payload["review"]["diagnosis"]["primary"], list)
        assert "focus_subskills" in payload["review"]["coaching_feedback"]
        assert payload["coach_continuity"]["teaching_plan"] is None
        assert payload["coach_continuity"]["teaching_plan_snapshot"] is None
        for subskill_id in payload["review"]["priority_subskills"]:
            evidence_items = payload["review"]["subskills"][subskill_id]["evidence"]
            assert any(
                isinstance(item, dict)
                and isinstance(item.get("turn_index"), int)
                and item["turn_index"] > 0
                for item in evidence_items
            )
        assert "progress_snapshot" in payload
        assert payload["progress_snapshot"]["learner_id"] == learner_id
        assert "coach_memory" in payload["progress_snapshot"]
        assert "practice_path" in payload["progress_snapshot"]
        assert 1 <= len(payload["progress_snapshot"]["practice_path"]) <= 3
        _assert_recommendation_shape(payload["progress_snapshot"]["latest_recommendations"][0])
        _assert_recommendation_shape(payload["progress_snapshot"]["practice_path"][0], step_index=1)
        assert payload["experiment_context"]["profile_id"] == "alpha_baseline_v1"

        review = client.get(f"/v1/sessions/{session_id}/review")
        assert review.status_code == 200
        review_payload = review.json()
        assert review_payload["session_id"] == session_id
        assert review_payload["status"] == "finalized"
        assert "overall_score" in review_payload["review"]
        assert review_payload["scenario"]["persona_label"]
        assert review_payload["coach_continuity"]["teaching_plan"] is None
        assert review_payload["coach_continuity"]["teaching_plan_snapshot"] is None
        assert "coach_memory" in review_payload
        assert review_payload["experiment_context"]["profile_id"] == "alpha_baseline_v1"
        for subskill_id in review_payload["review"]["priority_subskills"]:
            evidence_items = review_payload["review"]["subskills"][subskill_id]["evidence"]
            assert any(
                isinstance(item, dict)
                and isinstance(item.get("turn_index"), int)
                and item["turn_index"] > 0
                for item in evidence_items
            )

        progress = client.get(f"/v1/learners/{learner_id}/progress")
        assert progress.status_code == 200
        progress_payload = progress.json()
        assert progress_payload["learner_id"] == learner_id
        assert progress_payload["total_sessions"] == 1
        assert progress_payload["total_exp"] > 0
        assert isinstance(progress_payload["subskills"], dict)
        assert "weakness_clusters" in progress_payload
        assert isinstance(progress_payload["weakness_clusters"], list)
        assert "coach_memory" in progress_payload
        assert "curriculum" in progress_payload
        assert progress_payload["curriculum"]["current_stage_id"]
        assert progress_payload["curriculum"]["stage_position"] >= 1
        assert isinstance(progress_payload["curriculum"]["rationale"], str)
        assert progress_payload["curriculum"]["mastery_status"] in {
            "needs_practice",
            "improving",
            "stable",
            "mastered",
        }
        assert progress_payload["curriculum"]["review_status"] in {
            "focus_now",
            "maintain",
            "soon",
            "due",
        }
        assert isinstance(progress_payload["curriculum"]["attention_reason"], str)
        assert "skill_world" in progress_payload
        assert progress_payload["skill_world"]["summary"]["total_stage_count"] >= 1
        assert len(progress_payload["skill_world"]["nodes"]) >= 1
        assert progress_payload["skill_world"]["achievements"][0]["achievement_id"] == (
            "first_finalized_session"
        )
        first_subskill = next(iter(progress_payload["subskills"].values()))
        assert "rolling_average" in first_subskill
        assert "history_count" in first_subskill
        assert first_subskill["mastery_status"] in {
            "needs_practice",
            "improving",
            "stable",
            "mastered",
        }
        assert first_subskill["review_status"] in {
            "focus_now",
            "maintain",
            "soon",
            "due",
        }
        assert isinstance(first_subskill["status_reason"], str)
        recommendations = progress_payload["latest_recommendations"]
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
        first_recommendation = recommendations[0]
        assert first_recommendation["scenario_id"] != scenario_id
        assert isinstance(first_recommendation["title"], str)
        assert isinstance(first_recommendation["reason"], str)
        assert isinstance(first_recommendation["target_subskills"], list)
        _assert_recommendation_shape(first_recommendation)
        practice_path = progress_payload["practice_path"]
        assert isinstance(practice_path, list)
        assert 1 <= len(practice_path) <= 3
        _assert_recommendation_shape(practice_path[0], step_index=1)
        assert practice_path[0]["scenario_id"] == first_recommendation["scenario_id"]

        # Idempotency guard: repeated finish should not duplicate progression.
        finish_again = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish_again.status_code == 200
        progress_after_second_finish = client.get(f"/v1/learners/{learner_id}/progress")
        assert progress_after_second_finish.status_code == 200
        assert progress_after_second_finish.json()["total_sessions"] == 1


def test_send_turn_after_finalized_returns_409() -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_finalized_guard"},
        )
        session_id = started.json()["session_id"]

        client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "A concise evidence-backed opening with one next step."},
        )
        finished = client.post(f"/v1/sessions/{session_id}/finish")
        assert finished.status_code == 200

        response = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "One more retry after finalization."},
        )
    assert response.status_code == 409
    assert "already finalized" in response.json()["detail"]


def test_send_turn_after_awaiting_finish_returns_409() -> None:
    with TestClient(main.app) as client:
        scenarios_payload = client.get("/v1/scenarios").json()["scenarios"]
        busy_scenario = next(
            item for item in scenarios_payload if item["id"] == "busy_doctor_short_visit"
        )
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": busy_scenario["id"], "learner_id": "learner_turn_limit_guard"},
        )
        session_id = started.json()["session_id"]

        last_turn_payload = None
        for index in range(busy_scenario["max_turns"]):
            turn = client.post(
                f"/v1/sessions/{session_id}/turn",
                json={"message": f"Turn {index + 1} with one relevant evidence point."},
            )
            assert turn.status_code == 200
            last_turn_payload = turn.json()

        assert last_turn_payload is not None
        assert last_turn_payload["status"] == "awaiting_finish"

        response = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "An extra turn after the max-turn cutoff."},
        )
    assert response.status_code == 409
    assert "max turns" in response.json()["detail"].lower()


def test_send_turn_safety_scenario_prioritizes_reporting_process() -> None:
    with TestClient(main.app) as client:
        started = client.post(
            "/v1/sessions/start",
            json={
                "scenario_id": "adverse_event_followup_required",
                "learner_id": "learner_safety_turn",
            },
        )
        session_id = started.json()["session_id"]

        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "I want to share a product update and why it matters for more patients."},
        )
        assert turn.status_code == 200
        payload = turn.json()

        assert payload["director"]["phase"] == "safety"
        assert payload["director"]["recommended_action"] == "state_reporting_process_and_followup"
        assert "followup_process_not_stated" in payload["director"]["events"]
        assert "escalation" in payload["doctor_reply"].lower()


def test_send_turn_safety_reply_respects_japanese_locale() -> None:
    with TestClient(main.app) as client:
        started = client.post(
            "/v1/sessions/start",
            json={
                "scenario_id": "adverse_event_followup_required",
                "learner_id": "learner_safety_turn_ja",
                "locale": "ja",
            },
        )
        session_id = started.json()["session_id"]

        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "I want to share a product update and why it matters for more patients."},
        )
        assert turn.status_code == 200
        payload = turn.json()
        assert payload["director"]["phase"] == "safety"
        assert "報告" in payload["doctor_reply"]
        assert "フォロー" in payload["doctor_reply"]


def test_send_turn_safety_reply_respects_chinese_locale() -> None:
    with TestClient(main.app) as client:
        started = client.post(
            "/v1/sessions/start",
            json={
                "scenario_id": "adverse_event_followup_required",
                "learner_id": "learner_safety_turn_zh",
                "locale": "zh",
            },
        )
        session_id = started.json()["session_id"]

        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "I want to share a product update and why it matters for more patients."},
        )
        assert turn.status_code == 200
        payload = turn.json()
        assert payload["director"]["phase"] == "safety"
        assert "上报" in payload["doctor_reply"]
        assert "随访" in payload["doctor_reply"]


def test_send_turn_evidence_scenario_requests_endpoint_and_safety_detail() -> None:
    with TestClient(main.app) as client:
        started = client.post(
            "/v1/sessions/start",
            json={
                "scenario_id": "cautious_doctor_evidence_check",
                "learner_id": "learner_evidence_turn",
            },
        )
        session_id = started.json()["session_id"]

        first_turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "May I take 30 seconds to discuss one patient segment?"},
        )
        assert first_turn.status_code == 200

        second_turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "This has been working very well and should matter in practice."},
        )
        assert second_turn.status_code == 200
        payload = second_turn.json()

        assert payload["director"]["phase"] == "evidence"
        assert payload["director"]["recommended_action"] == "cite_endpoint_safety_and_patient_segment"
        assert "endpoint" in payload["doctor_reply"].lower()
        assert "safety" in payload["doctor_reply"].lower()


def test_send_turn_busy_scenario_enters_closing_before_last_turn() -> None:
    with TestClient(main.app) as client:
        started = client.post(
            "/v1/sessions/start",
            json={
                "scenario_id": "busy_doctor_short_visit",
                "learner_id": "learner_busy_closing",
            },
        )
        session_id = started.json()["session_id"]

        last_turn_payload = None
        for _ in range(6):
            turn = client.post(
                f"/v1/sessions/{session_id}/turn",
                json={"message": "May I share one relevant point for a defined patient segment?"},
            )
            assert turn.status_code == 200
            last_turn_payload = turn.json()

        assert last_turn_payload is not None
        assert last_turn_payload["director"]["phase"] == "closing"
        assert last_turn_payload["director"]["recommended_action"] == "state_micro_commitment_and_followup"
        assert "limited next step" in last_turn_payload["doctor_reply"].lower()


def test_session_resume_and_review_survive_restart() -> None:
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios")
        scenario_id = scenarios.json()["scenarios"][0]["id"]

        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_002"},
        )
        session_id = started.json()["session_id"]
        first_turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "Short opening to set context for this doctor."},
        )
        assert first_turn.status_code == 200

    # New app lifespan => in-memory engine reset. Persisted session should still be recoverable.
    with TestClient(main.app) as restarted_client:
        second_turn = restarted_client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "I can share evidence and a practical next step."},
        )
        assert second_turn.status_code == 200

        finished = restarted_client.post(f"/v1/sessions/{session_id}/finish")
        assert finished.status_code == 200
        assert finished.json()["status"] == "finalized"

        review = restarted_client.get(f"/v1/sessions/{session_id}/review")
        assert review.status_code == 200
        assert review.json()["session_id"] == session_id
        assert review.json()["status"] == "finalized"


def test_session_prompt_context_is_frozen_across_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_prompt_freeze"},
        )
        session_id = started.json()["session_id"]
        assert started.json()["experiment_context"]["profile_id"] == "alpha_baseline_v1"

        first_turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "Short opening with one practical evidence point."},
        )
        assert first_turn.status_code == 200

    monkeypatch.setenv("MR_RUNTIME_PROMPT_PROFILE", "alpha_coach_concise_v1")
    monkeypatch.setenv("MR_RUNTIME_EXPERIMENT_ID", "coach-canary-1")
    monkeypatch.setenv("MR_RUNTIME_EXPERIMENT_FLAGS", "manual_override")

    with TestClient(main.app) as restarted_client:
        finished = restarted_client.post(f"/v1/sessions/{session_id}/finish")
        assert finished.status_code == 200
        payload = finished.json()
        prompting = payload["review"]["meta"]["prompting"]
        assert prompting["profile_id"] == "alpha_baseline_v1"
        assert prompting["experiment_id"] is None
        assert prompting["contracts"]["coach"]["version"] == 1
        assert "manual_override" not in prompting["flags"]


def test_progress_snapshot_survives_restart() -> None:
    learner_id = f"test_learner_{uuid.uuid4().hex[:8]}"
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios")
        scenario_id = scenarios.json()["scenarios"][0]["id"]
        session_id = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": learner_id},
        ).json()["session_id"]
        client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "I will keep this concise and evidence-based."},
        )
        finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish.status_code == 200

    with TestClient(main.app) as restarted_client:
        progress = restarted_client.get(f"/v1/learners/{learner_id}/progress")
        assert progress.status_code == 200
        payload = progress.json()
        assert payload["learner_id"] == learner_id
        assert payload["total_sessions"] == 1
        assert payload["total_exp"] > 0
        assert "weakness_clusters" in payload
        assert "curriculum" in payload
        assert 1 <= len(payload["practice_path"]) <= 3
        _assert_recommendation_shape(payload["practice_path"][0], step_index=1)


def test_next_session_receives_coach_continuity_from_prior_progress() -> None:
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios").json()["scenarios"]
        first_scenario_id = scenarios[0]["id"]
        second_scenario_id = scenarios[1]["id"]

        first_session_id = client.post(
            "/v1/sessions/start",
            json={"scenario_id": first_scenario_id, "learner_id": "learner_memory_001"},
        ).json()["session_id"]
        client.post(
            f"/v1/sessions/{first_session_id}/turn",
            json={"message": "One short opening with weak discovery."},
        )
        finished = client.post(f"/v1/sessions/{first_session_id}/finish")
        assert finished.status_code == 200

        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": second_scenario_id, "learner_id": "learner_memory_001"},
        )
        assert started.status_code == 200
        payload = started.json()
        assert payload["coach_continuity"]["carryover_focus_subskills"]
        assert payload["coach_continuity"]["next_actions"]
        second_session_id = payload["session_id"]
        session_state = client.get(f"/v1/sessions/{second_session_id}")
        assert session_state.status_code == 200
        session_state_payload = session_state.json()
        snapshot = _assert_teaching_plan_snapshot(
            payload["coach_continuity"],
            session_id=second_session_id,
            source_session_id=first_session_id,
        )
        assert snapshot["source_scenario_id"] == first_scenario_id
        prior_evidence = payload["coach_continuity"]["teaching_plan"]["prior_evidence"]
        assert isinstance(prior_evidence, list)
        assert len(prior_evidence) > 0
        assert isinstance(prior_evidence[0]["summary"], str)
        assert prior_evidence[0]["summary"]
        _assert_teaching_plan_snapshot(
            session_state_payload["coach_continuity"],
            session_id=second_session_id,
            frozen_at=session_state_payload["started_at"],
            source_session_id=first_session_id,
        )

        events = client.get(f"/v1/sessions/{second_session_id}/events")
        assert events.status_code == 200
        started_event = next(
            item for item in events.json()["events"] if item["type"] == "session_started"
        )
        event_snapshot = started_event["content"]["coach_continuity"]["teaching_plan_snapshot"]
        assert event_snapshot["snapshot_id"] == f"tp_{second_session_id}"
        assert event_snapshot["plan_version"] == 1
        assert event_snapshot["source_session_id"] == first_session_id
        assert started_event["content"]["coach_continuity"]["teaching_plan"]["version"] == 1


def test_review_keeps_frozen_session_teaching_plan_after_later_sessions() -> None:
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios").json()["scenarios"]
        assert len(scenarios) >= 3
        scenario_a = scenarios[0]["id"]
        scenario_b = scenarios[1]["id"]
        scenario_c = scenarios[2]["id"]

        first_session_id = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_a, "learner_id": "learner_frozen_review_001"},
        ).json()["session_id"]
        client.post(
            f"/v1/sessions/{first_session_id}/turn",
            json={"message": "A short opening that still needs stronger discovery."},
        )
        first_finished = client.post(f"/v1/sessions/{first_session_id}/finish")
        assert first_finished.status_code == 200

        second_started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_b, "learner_id": "learner_frozen_review_001"},
        )
        assert second_started.status_code == 200
        second_started_payload = second_started.json()
        second_session_id = second_started_payload["session_id"]
        second_session_state = client.get(f"/v1/sessions/{second_session_id}")
        assert second_session_state.status_code == 200
        second_started_at = second_session_state.json()["started_at"]
        frozen_snapshot = _assert_teaching_plan_snapshot(
            second_started_payload["coach_continuity"],
            session_id=second_session_id,
            source_session_id=first_session_id,
        )
        assert frozen_snapshot["source_scenario_id"] == scenario_a
        frozen_prior_evidence = second_started_payload["coach_continuity"]["teaching_plan"]["prior_evidence"]
        assert isinstance(frozen_prior_evidence, list)
        assert len(frozen_prior_evidence) > 0
        client.post(
            f"/v1/sessions/{second_session_id}/turn",
            json={"message": "One concise evidence-backed point with a next step."},
        )
        second_finished = client.post(f"/v1/sessions/{second_session_id}/finish")
        assert second_finished.status_code == 200

        third_session_id = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_c, "learner_id": "learner_frozen_review_001"},
        ).json()["session_id"]
        client.post(
            f"/v1/sessions/{third_session_id}/turn",
            json={"message": "A sharper follow-up with one relevant patient segment."},
        )
        third_finished = client.post(f"/v1/sessions/{third_session_id}/finish")
        assert third_finished.status_code == 200

        review = client.get(f"/v1/sessions/{second_session_id}/review")
        assert review.status_code == 200
        review_payload = review.json()
        review_snapshot = _assert_teaching_plan_snapshot(
            review_payload["coach_continuity"],
            session_id=second_session_id,
            frozen_at=second_started_at,
            source_session_id=first_session_id,
        )
        assert review_snapshot["source_scenario_id"] == scenario_a
        assert (
            review_payload["coach_continuity"]["teaching_plan"]["prior_evidence"]
            == frozen_prior_evidence
        )
        assert review_payload["coach_memory"]["last_session"]["session_id"] == third_session_id
        assert review_payload["coach_memory"]["teaching_plan"]["version"] == 1
        assert review_payload["coach_memory"]["last_teaching_plan_achievement"]["status"] in {
            "achieved",
            "partially_achieved",
            "not_achieved",
            "no_plan",
        }


def test_get_session_events_returns_recorded_events() -> None:
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios")
        scenario_id = scenarios.json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_004"},
        )
        session_id = started.json()["session_id"]

        client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "Sharing one concrete point for relevant patient profile."},
        )
        client.post(f"/v1/sessions/{session_id}/finish")

        events = client.get(f"/v1/sessions/{session_id}/events")
        assert events.status_code == 200
        payload = events.json()
        assert payload["session_id"] == session_id
        assert payload["event_count"] >= 3
        event_types = [item["type"] for item in payload["events"]]
        assert "session_started" in event_types
        assert "turn_processed" in event_types
        assert "session_finalized" in event_types
        started_event = next(item for item in payload["events"] if item["type"] == "session_started")
        turn_event = next(item for item in payload["events"] if item["type"] == "turn_processed")
        finalized_event = next(item for item in payload["events"] if item["type"] == "session_finalized")
        assert started_event["source"] == "runtime"
        assert started_event["stage"] == "opening"
        assert started_event["schema_version"] == "1.1"
        assert started_event["seq"] == 1
        assert started_event["content"]["experiment_context"]["profile_id"] == "alpha_baseline_v1"
        assert started_event["content"]["coach_continuity"]["summary"]
        assert started_event["content"]["taxonomy"]["categories"] == ["opening"]
        assert turn_event["content"]["director_events"]
        assert turn_event["content"]["signal_summary"]["token_count"] > 0
        assert turn_event["content"]["taxonomy"]["categories"]
        assert turn_event["content"]["director"]["phase"] == turn_event["stage"]
        assert turn_event["seq"] == 2
        assert finalized_event["content"]["experiment_context"]["contracts"]["coach"]["version"] == 1
        assert finalized_event["stage"] == "completion"
        assert finalized_event["content"]["taxonomy"]["categories"] == ["completion"]
        assert started_event["metadata"]["action_id"] == "start_session"
        assert started_event["metadata"]["skill_id"] == "mr_visit_jp"
        assert turn_event["metadata"]["action_id"] == "send_turn"
        assert turn_event["metadata"]["turn_id"] == f"{session_id}:turn:0001"
        assert finalized_event["metadata"]["action_id"] == "finish_session"
        trace_ids = {
            item["metadata"]["trace_id"]
            for item in payload["events"]
            if isinstance(item.get("metadata"), dict)
        }
        assert len(trace_ids) == 1


@pytest.mark.skipif(
    os.environ.get("MR_RUNTIME_PERSISTENCE_MODE") == "sql",
    reason="file-persistence specific (reads filesystem paths directly)",
)
def test_persisted_session_keeps_turn_transcript_and_event_order(
    isolate_runtime_data_dir: Path,
) -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_persistence_001"},
        )
        session_id = started.json()["session_id"]

        first_message = "Short opening with one clinically relevant segment."
        second_message = "Evidence-backed follow-up and a realistic next step."
        client.post(f"/v1/sessions/{session_id}/turn", json={"message": first_message})
        client.post(f"/v1/sessions/{session_id}/turn", json={"message": second_message})
        finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish.status_code == 200

    session_file = isolate_runtime_data_dir / "sessions" / f"{session_id}.json"
    event_file = isolate_runtime_data_dir / "events" / f"{session_id}.jsonl"
    assert session_file.exists()
    assert event_file.exists()

    session_payload = json.loads(session_file.read_text(encoding="utf-8"))
    assert session_payload["session_id"] == session_id
    assert session_payload["turn_count"] == 2
    assert session_payload["prompt_context"]["profile_id"] == "alpha_baseline_v1"
    assert session_payload["prompt_context"]["contracts"]["coach"]["version"] == 1
    assert session_payload["continuity_context"]["summary"]
    assert session_payload["context"]["skill_id"] == "mr_visit_jp"
    assert session_payload["context"]["scenario_id"] == scenario_id
    assert session_payload["context"]["learner_id"] == "learner_persistence_001"
    assert session_payload["context"]["prompt_profile"] == "alpha_baseline_v1"
    assert [item["user_message"] for item in session_payload["turns"]] == [
        first_message,
        second_message,
    ]
    assert session_payload["review"]["overall_score"] >= 0
    assert session_payload["review"]["meta"]["context"]["session_id"] == session_id

    event_lines = [line for line in event_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    events = [json.loads(line) for line in event_lines]
    event_types = [item["type"] for item in events]
    assert event_types == [
        "session_started",
        "turn_processed",
        "turn_processed",
        "session_finalized",
    ]
    trace_ids = {
        item["metadata"]["trace_id"]
        for item in events
        if isinstance(item.get("metadata"), dict)
    }
    assert trace_ids == {session_payload["context"]["trace_id"]}
    assert [item["seq"] for item in events] == [1, 2, 3, 4]
    assert events[0]["content"]["coach_continuity"]["summary"]
    assert events[1]["content"]["turn_index"] == 1
    assert events[1]["content"]["signal_summary"]["token_count"] > 0
    assert events[1]["content"]["taxonomy"]["entries"]
    assert events[-1]["stage"] == "completion"
    assert events[-1]["schema_version"] == "1.1"
    assert events[-1]["content"]["finish_reason"] == session_payload["finish_reason"]


@pytest.mark.skipif(
    os.environ.get("MR_RUNTIME_PERSISTENCE_MODE") == "sql",
    reason="file-persistence specific (reads filesystem paths directly)",
)
def test_repeat_finish_does_not_append_duplicate_finalization_event(
    isolate_runtime_data_dir: Path,
) -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_retry_finish"},
        )
        session_id = started.json()["session_id"]

        client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "One concise turn with a practical follow-up path."},
        )
        first_finish = client.post(f"/v1/sessions/{session_id}/finish")
        second_finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert first_finish.status_code == 200
        assert second_finish.status_code == 200

    event_file = isolate_runtime_data_dir / "events" / f"{session_id}.jsonl"
    event_types = [
        json.loads(line)["type"]
        for line in event_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert event_types.count("session_finalized") == 1


def test_compliance_risk_is_tagged_in_review() -> None:
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios")
        scenario_id = scenarios.json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_005"},
        )
        session_id = started.json()["session_id"]

        risky_turn = (
            "I guarantee 100% response and the competitor is worse for every patient profile."
        )
        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": risky_turn},
        )
        assert turn.status_code == 200

        finished = client.post(f"/v1/sessions/{session_id}/finish")
        assert finished.status_code == 200
        review = finished.json()["review"]
        compliance_flags = review.get("compliance_flags", [])
        assert isinstance(compliance_flags, list)
        assert len(compliance_flags) > 0

        flag_ids = {flag.get("rule_id") for flag in compliance_flags if isinstance(flag, dict)}
        assert "unsupported_outcome_promise" in flag_ids or "unsubstantiated_competitor_comparison" in flag_ids


def test_compliance_risk_biases_next_recommendations_toward_safer_drills() -> None:
    learner_id = f"test_learner_{uuid.uuid4().hex[:8]}"
    with TestClient(main.app) as client:
        scenarios = client.get("/v1/scenarios")
        scenario_id = scenarios.json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": learner_id},
        )
        session_id = started.json()["session_id"]

        risky_turn = (
            "I guarantee 100% response and the competitor is worse for every patient profile."
        )
        client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": risky_turn},
        )
        finished = client.post(f"/v1/sessions/{session_id}/finish")
        assert finished.status_code == 200

        recommendations = finished.json()["progress_snapshot"]["latest_recommendations"]
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

        top_two_difficulties = {item["difficulty"] for item in recommendations[:2]}
        assert "hard" not in top_two_difficulties

        assert all(item["recommendation_type"] == "compliance" for item in recommendations[:2])
        assert all(
            "compliance risk detected" in str(item.get("evidence_source", "")).lower()
            for item in recommendations[:2]
        )


def test_finish_session_returns_500_when_schema_gate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = get_domain_bundle()
    broken_bundle = replace(
        bundle,
        coach_feedback_schema={
            "type": "object",
            "required": ["impossible_field"],
            "properties": {"impossible_field": {"type": "string"}},
            "additionalProperties": False,
        },
    )

    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "get_domain_bundle", lambda: broken_bundle)
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_schema_gate"},
        )
        session_id = started.json()["session_id"]
        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "I will provide one practical evidence-backed update."},
        )
        assert turn.status_code == 200

        finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish.status_code == 500
        assert "Review artifact validation failed" in finish.json()["detail"]


def test_invalid_model_output_falls_back_to_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenModelGenerator:
        def generate(self, **_: object) -> dict[str, object]:
            return {
                "judge_review": {"invalid": True},
                "coaching_feedback": {"invalid": True},
                "compliance_flags": [{"invalid": True}],
                "model_meta": {"generator": "broken_test"},
            }

    monkeypatch.setattr(main, "build_model_artifact_generator", lambda: BrokenModelGenerator())

    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_model_fallback"},
        )
        session_id = started.json()["session_id"]
        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "Keep this concise and clinically relevant with evidence."},
        )
        assert turn.status_code == 200

        finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish.status_code == 200
        review = finish.json()["review"]
        assert review["meta"]["artifact_sources"]["judge"] == "rule"
        assert review["meta"]["artifact_sources"]["coach"] == "rule"
        assert review["meta"]["artifact_sources"]["compliance"] == "rule"
        reasons = review["meta"]["fallback_reasons"]
        assert any("model_judge_failed" in item for item in reasons)
        assert any("model_coach_failed" in item for item in reasons)
        assert any("model_compliance_failed" in item for item in reasons)


def test_model_parse_error_falls_back_to_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ParseErrorModelGenerator:
        def generate(self, **_: object) -> dict[str, object]:
            raise RuntimeError("openai_compat_parse_failed: choices is missing or empty")

    monkeypatch.setattr(main, "build_model_artifact_generator", lambda: ParseErrorModelGenerator())

    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_parse_fallback"},
        )
        session_id = started.json()["session_id"]
        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "Keep this clinically relevant and concise."},
        )
        assert turn.status_code == 200

        finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish.status_code == 200
        review = finish.json()["review"]
        assert review["meta"]["artifact_sources"]["judge"] == "rule"
        assert review["meta"]["artifact_sources"]["coach"] == "rule"
        assert review["meta"]["artifact_sources"]["compliance"] == "rule"
        reasons = review["meta"]["fallback_reasons"]
        assert any("model_generator_error: openai_compat_parse_failed" in item for item in reasons)


def test_mock_mode_review_meta_marks_artifacts_as_mock() -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_mock_meta"},
        )
        session_id = started.json()["session_id"]
        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "Keep this practical, brief, and supported by one proof point."},
        )
        assert turn.status_code == 200

        finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish.status_code == 200
        review = finish.json()["review"]
        artifact_sources = review["meta"]["artifact_sources"]
        artifact_modes = review["meta"]["artifact_modes"]
        assert set(artifact_sources.keys()) == {"judge", "coach", "compliance"}
        assert set(artifact_modes.keys()) == {"judge", "coach", "compliance"}
        for key, source in artifact_sources.items():
            assert source in {"model", "rule"}
            expected_mode = "mock" if source == "model" else "rule"
            assert artifact_modes[key] == expected_mode
        assert review["meta"]["model_meta"]["generator"] == "mock"


def test_structured_model_generation_error_records_rule_fallback_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StructuredFailureModelGenerator:
        def describe(self) -> dict[str, object]:
            return {
                "generator": "openai_compat",
                "requested_mode": "openai_compat",
                "artifact_mode": "model",
            }

        def generate(self, **_: object) -> dict[str, object]:
            raise ModelArtifactGenerationError(
                "openai_compat_call_failed[network] after 2 attempt(s): timed out",
                meta={
                    "generator": "openai_compat",
                    "requested_mode": "openai_compat",
                    "artifact_mode": "model",
                    "failure_stage": "network_error",
                    "attempt_count": 2,
                    "retry_count": 1,
                    "fallback_target": "rule",
                    "retryable": True,
                },
            )

    monkeypatch.setattr(main, "build_model_artifact_generator", lambda: StructuredFailureModelGenerator())

    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_structured_failure"},
        )
        session_id = started.json()["session_id"]
        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "Keep this clinically grounded and concise."},
        )
        assert turn.status_code == 200

        finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish.status_code == 200
        review = finish.json()["review"]
        assert review["meta"]["artifact_modes"] == {
            "judge": "rule",
            "coach": "rule",
            "compliance": "rule",
        }
        assert review["meta"]["model_meta"]["generator"] == "openai_compat"
        assert review["meta"]["model_meta"]["failure_stage"] == "network_error"
        assert review["meta"]["model_meta"]["attempt_count"] == 2
        assert review["meta"]["model_meta"]["fallback_target"] == "rule"
        reasons = review["meta"]["fallback_reasons"]
        assert any("model_generator_error: openai_compat_call_failed[network]" in item for item in reasons)


def test_generic_model_generation_error_records_fallback_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GenericFailureModelGenerator:
        def describe(self) -> dict[str, object]:
            return {
                "generator": "openai_compat",
                "requested_mode": "openai_compat",
                "artifact_mode": "model",
            }

        def generate(self, **_: object) -> dict[str, object]:
            raise RuntimeError("unexpected provider adapter crash")

    monkeypatch.setattr(main, "build_model_artifact_generator", lambda: GenericFailureModelGenerator())

    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_generic_failure"},
        )
        session_id = started.json()["session_id"]
        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={"message": "Use one practical evidence point and keep it brief."},
        )
        assert turn.status_code == 200

        finish = client.post(f"/v1/sessions/{session_id}/finish")
        assert finish.status_code == 200
        review = finish.json()["review"]
        assert review["meta"]["model_meta"]["generator"] == "openai_compat"
        assert review["meta"]["model_meta"]["failure_stage"] == "generator_exception"
        assert review["meta"]["model_meta"]["error_type"] == "RuntimeError"
        assert review["meta"]["model_meta"]["fallback_target"] == "rule"
        assert review["meta"]["model_meta"]["error_detail"] == "unexpected provider adapter crash"


def test_organization_reports_aggregate_sessions_and_block_supervisor_transcripts() -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]

        first_finished = _start_and_finish_session(
            client,
            scenario_id=scenario_id,
            learner_id="learner_team_alpha",
        )
        _start_and_finish_session(
            client,
            scenario_id=scenario_id,
            learner_id="learner_team_alpha",
            message="Ask one discovery question before sharing the evidence point.",
        )
        _start_and_finish_session(
            client,
            scenario_id=scenario_id,
            learner_id="learner_team_beta",
            message="Anchor the value proposition to one specific patient segment.",
        )
        active = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_team_beta"},
        )
        assert active.status_code == 200, active.json()

        reports = client.get(
            "/v1/organizations/local/reports",
            headers={"X-Viewer-Role": "supervisor"},
        )
        assert reports.status_code == 200, reports.json()
        payload = reports.json()

        assert payload["organization_scope"] == "global"
        assert payload["team_summary"]["learner_count"] == 2
        assert payload["team_summary"]["total_sessions"] == 4
        assert payload["team_summary"]["finalized_sessions"] == 3
        assert payload["team_summary"]["active_sessions"] == 1
        assert payload["team_summary"]["practice_completion_rate"] == 0.75
        learner_rows = {item["learner_id"]: item for item in payload["learners"]}
        assert learner_rows["learner_team_alpha"]["total_sessions"] == 2
        assert learner_rows["learner_team_beta"]["active_sessions"] == 1
        assert len(learner_rows["learner_team_alpha"]["recent_reviews"]) == 2
        recent_review_ids = {
            item["session_id"]
            for item in learner_rows["learner_team_alpha"]["recent_reviews"]
        }
        assert first_finished["session_id"] in recent_review_ids

        session_id = str(first_finished["session_id"])
        session = client.get(
            f"/v1/sessions/{session_id}",
            headers={"X-Viewer-Role": "supervisor"},
        )
        assert session.status_code == 403
        assert "raw session transcripts" in session.json()["detail"]

        events = client.get(
            f"/v1/sessions/{session_id}/events",
            headers={"X-Viewer-Role": "supervisor"},
        )
        assert events.status_code == 403
        assert "raw session transcripts" in events.json()["detail"]

        review = client.get(
            f"/v1/sessions/{session_id}/review",
            headers={"X-Viewer-Role": "supervisor"},
        )
        assert review.status_code == 200
        assert review.json()["session_id"] == session_id


def test_organization_reports_honor_org_scope_and_review_isolation() -> None:
    with TestClient(main.app) as client:
        scenario_id = client.get("/v1/scenarios").json()["scenarios"][0]["id"]
        headers_a = {"X-Org-ID": "org_a"}
        headers_b = {"X-Org-ID": "org_b"}

        finished_a = _start_and_finish_session(
            client,
            scenario_id=scenario_id,
            learner_id="learner_org_a",
            headers=headers_a,
        )
        _start_and_finish_session(
            client,
            scenario_id=scenario_id,
            learner_id="learner_org_b",
            headers=headers_b,
        )

        report_a = client.get("/v1/organizations/org_a/reports", headers=headers_a)
        assert report_a.status_code == 200, report_a.json()
        payload_a = report_a.json()
        assert payload_a["organization_id"] == "org_a"
        assert payload_a["organization_scope"] == "organization"
        assert payload_a["team_summary"]["learner_count"] == 1
        assert payload_a["team_summary"]["total_sessions"] == 1
        assert [item["learner_id"] for item in payload_a["learners"]] == ["learner_org_a"]

        forbidden_scope = client.get("/v1/organizations/local/reports", headers=headers_a)
        assert forbidden_scope.status_code == 403
        assert "cannot access the unscoped organization report" in forbidden_scope.json()["detail"]

        mismatched_scope = client.get("/v1/organizations/org_b/reports", headers=headers_a)
        assert mismatched_scope.status_code == 403
        assert "does not match" in mismatched_scope.json()["detail"]

        review = client.get(
            f"/v1/sessions/{finished_a['session_id']}/review",
            headers=headers_b,
        )
        assert review.status_code == 404
