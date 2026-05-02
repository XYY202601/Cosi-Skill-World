from __future__ import annotations

import importlib.util
import logging
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from runtime_contract_fixture import (
    OPTIONAL_RUNTIME_ACTION_FIXTURES,
    REQUIRED_RUNTIME_ACTION_FIXTURES,
    assert_payload_schema,
    assert_runtime_health_payload,
    assert_skill_summary_supports_required_runtime_contract,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
HERMES_SRC = REPO_ROOT / "apps" / "hermes-orchestrator" / "src"
RUNTIME_SRC = REPO_ROOT / "apps" / "mr-visit-jp-runtime" / "src"
GP_RUNTIME_SRC = REPO_ROOT / "apps" / "gp-visit-jp-runtime" / "src"


def _load_module(alias: str, path: Path, prepend_paths: list[Path]) -> object:
    original_sys_path = list(sys.path)
    original_providers = sys.modules.pop("providers", None)
    for candidate in reversed(prepend_paths):
        candidate_str = str(candidate)
        if candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)

    try:
        providers_init = path.parent / "providers" / "__init__.py"
        if providers_init.exists():
            providers_spec = importlib.util.spec_from_file_location(
                "providers",
                providers_init,
                submodule_search_locations=[str(providers_init.parent)],
            )
            if providers_spec is None or providers_spec.loader is None:
                raise RuntimeError(f"Failed to load providers package: {providers_init}")
            providers_module = importlib.util.module_from_spec(providers_spec)
            sys.modules["providers"] = providers_module
            providers_spec.loader.exec_module(providers_module)

        spec = importlib.util.spec_from_file_location(alias, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load module: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[alias] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("providers", None)
        if original_providers is not None:
            sys.modules["providers"] = original_providers
        sys.path[:] = original_sys_path


@pytest.fixture
def hermes_runtime_apps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runtime_data = tmp_path / "runtime-data"
    gp_runtime_data = tmp_path / "gp-runtime-data"
    hermes_data = tmp_path / "hermes-data"
    monkeypatch.setenv("MR_RUNTIME_DATA_DIR", str(runtime_data))
    monkeypatch.setenv("HERMES_DATA_DIR", str(hermes_data))
    monkeypatch.setenv("MR_RUNTIME_MODEL_MODE", "mock")
    monkeypatch.setenv("GP_VISIT_JP_RUNTIME_BASE", "http://127.0.0.1:8200")

    runtime_main = _load_module(
        alias=f"mr_runtime_main_{uuid.uuid4().hex}",
        path=RUNTIME_SRC / "main.py",
        prepend_paths=[RUNTIME_SRC],
    )
    runtime_main.get_domain_bundle.cache_clear()

    gp_runtime_main = _load_module(
        alias=f"gp_runtime_main_{uuid.uuid4().hex}",
        path=GP_RUNTIME_SRC / "main.py",
        prepend_paths=[GP_RUNTIME_SRC],
    )
    gp_runtime_main.app.state.sessions = {}
    gp_runtime_main.app.state.events = {}
    gp_runtime_main.app.state.progress = {}

    hermes_main = _load_module(
        alias=f"hermes_main_{uuid.uuid4().hex}",
        path=HERMES_SRC / "main.py",
        prepend_paths=[HERMES_SRC, RUNTIME_SRC],
    )

    return hermes_main, runtime_main, gp_runtime_main


def test_hermes_proxies_full_session_flow_to_runtime(
    hermes_runtime_apps: tuple[object, object, object],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    hermes_main, runtime_main, gp_runtime_main = hermes_runtime_apps
    forwarded_headers: list[dict[str, str] | None] = []
    forwarded_requests: list[tuple[str, str]] = []
    last_runtime_result: dict[str, object] = {}
    caplog.set_level(logging.INFO)

    with TestClient(runtime_main.app) as runtime_client:
        runtime_health = runtime_client.get("/healthz")
        assert runtime_health.status_code == 200
        assert_runtime_health_payload(runtime_health.json())
        with TestClient(gp_runtime_main.app) as gp_runtime_client:

            async def _forward(
                *,
                path: str,
                method: str = "GET",
                json_body=None,
                runtime_api_base: str | None = None,
                headers: dict[str, str] | None = None,
            ):
                forwarded_headers.append(headers)
                forwarded_requests.append((method, path))
                client = gp_runtime_client if runtime_api_base == "http://127.0.0.1:8200" else runtime_client
                if method == "GET":
                    response = client.get(path, headers=headers)
                elif method == "POST":
                    response = client.post(path, json=json_body, headers=headers)
                else:
                    raise AssertionError(f"Unexpected method: {method}")
                payload = response.json() if response.text else {}
                trace_headers = {
                    key: value
                    for key in (
                        "x-request-id",
                        "x-trace-id",
                        "x-session-id",
                        "x-turn-id",
                        "x-service-name",
                    )
                    if (value := response.headers.get(key)) is not None
                }
                last_runtime_result["status"] = response.status_code
                last_runtime_result["payload"] = payload
                last_runtime_result["headers"] = trace_headers
                return hermes_main.RuntimeProxyResult(
                    status=response.status_code,
                    payload=payload,
                    headers=trace_headers,
                )

            monkeypatch.setattr(hermes_main, "proxy_runtime_request", _forward)

            with TestClient(hermes_main.app) as hermes_client:
                skills = hermes_client.get("/v1/skills")
                assert skills.status_code == 200
                assert skills.json()["skills"] == ["gp_visit_jp", "mr_visit_jp"]
                assert skills.json()["default_skill_id"] == "mr_visit_jp"
                items_by_id = {item["id"]: item for item in skills.json()["items"]}
                assert items_by_id["mr_visit_jp"]["runtime"]["base_url_env"] == "MR_VISIT_JP_RUNTIME_BASE"
                assert items_by_id["gp_visit_jp"]["runtime"]["base_url_env"] == "GP_VISIT_JP_RUNTIME_BASE"
                assert_skill_summary_supports_required_runtime_contract(items_by_id["mr_visit_jp"])
                assert_skill_summary_supports_required_runtime_contract(items_by_id["gp_visit_jp"])

                gates = hermes_client.get("/v1/evaluation-gates")
                assert gates.status_code == 200
                assert gates.json()["domain_id"] == "mr_visit_jp"
                assert gates.status_code == last_runtime_result["status"]
                assert gates.json() == last_runtime_result["payload"]
                assert_payload_schema(
                    gates.json(),
                    OPTIONAL_RUNTIME_ACTION_FIXTURES[0].response_schema,
                )

                skill_scoped_gates = hermes_client.get("/v1/skills/mr_visit_jp/evaluation-gates")
                assert skill_scoped_gates.status_code == 200
                assert skill_scoped_gates.json()["default_profile_id"] == "alpha_baseline_v1"
                assert skill_scoped_gates.status_code == last_runtime_result["status"]
                assert skill_scoped_gates.json() == last_runtime_result["payload"]

                scenarios = hermes_client.get("/v1/scenarios")
                assert scenarios.status_code == 200
                scenario_id = scenarios.json()["scenarios"][0]["id"]
                assert scenarios.status_code == last_runtime_result["status"]
                assert scenarios.json() == last_runtime_result["payload"]
                assert_payload_schema(
                    scenarios.json(),
                    REQUIRED_RUNTIME_ACTION_FIXTURES[0].response_schema,
                )

                started = hermes_client.post(
                    "/v1/sessions/start",
                    headers={
                        "x-request-id": "req_hermes_start_001",
                        "x-trace-id": "trace_hermes_chain_001",
                    },
                    json={"scenario_id": scenario_id, "learner_id": "learner_hermes_001"},
                )
                assert started.status_code == 200
                session_id = started.json()["session_id"]
                assert started.headers["x-request-id"] == "req_hermes_start_001"
                assert started.headers["x-trace-id"] == "trace_hermes_chain_001"
                assert started.headers["x-session-id"] == session_id
                assert started.headers["x-service-name"] == "hermes-orchestrator"
                assert started.status_code == last_runtime_result["status"]
                assert started.json() == last_runtime_result["payload"]
                assert forwarded_headers[-1] == {
                    "x-request-id": "req_hermes_start_001",
                    "x-trace-id": "trace_hermes_chain_001",
                }
                assert_payload_schema(
                    started.json(),
                    REQUIRED_RUNTIME_ACTION_FIXTURES[1].response_schema,
                )

                session = hermes_client.get(f"/v1/sessions/{session_id}")
                assert session.status_code == 200
                assert session.json()["session_id"] == session_id
                assert session.status_code == last_runtime_result["status"]
                assert session.json() == last_runtime_result["payload"]
                assert_payload_schema(
                    session.json(),
                    REQUIRED_RUNTIME_ACTION_FIXTURES[2].response_schema,
                )

                skill_scoped_turn = hermes_client.post(
                    f"/v1/skills/mr_visit_jp/sessions/{session_id}/turn",
                    headers={"x-request-id": "req_hermes_turn_001"},
                    json={"message": "One concise evidence-based update for this doctor."},
                )
                assert skill_scoped_turn.status_code == 200
                assert skill_scoped_turn.headers["x-request-id"] == "req_hermes_turn_001"
                assert skill_scoped_turn.headers["x-trace-id"] == "trace_hermes_chain_001"
                assert skill_scoped_turn.headers["x-session-id"] == session_id
                assert skill_scoped_turn.headers["x-turn-id"] == f"{session_id}:turn:0001"
                assert skill_scoped_turn.status_code == last_runtime_result["status"]
                assert skill_scoped_turn.json() == last_runtime_result["payload"]
                assert_payload_schema(
                    skill_scoped_turn.json(),
                    REQUIRED_RUNTIME_ACTION_FIXTURES[3].response_schema,
                )

                events = hermes_client.get(f"/v1/sessions/{session_id}/events")
                assert events.status_code == 200
                assert events.json()["session_id"] == session_id
                assert events.json()["event_count"] >= 2
                assert events.status_code == last_runtime_result["status"]
                assert events.json() == last_runtime_result["payload"]
                assert_payload_schema(
                    events.json(),
                    REQUIRED_RUNTIME_ACTION_FIXTURES[6].response_schema,
                )

                finished = hermes_client.post(f"/v1/sessions/{session_id}/finish")
                assert finished.status_code == 200
                assert finished.status_code == last_runtime_result["status"]
                assert finished.json() == last_runtime_result["payload"]
                progress_snapshot = finished.json()["progress_snapshot"]
                assert progress_snapshot["learner_id"] == "learner_hermes_001"
                assert len(progress_snapshot["latest_recommendations"]) > 0
                assert_payload_schema(
                    finished.json(),
                    REQUIRED_RUNTIME_ACTION_FIXTURES[4].response_schema,
                )

                review = hermes_client.get(f"/v1/sessions/{session_id}/review")
                assert review.status_code == 200
                assert review.json()["status"] == "finalized"
                assert review.status_code == last_runtime_result["status"]
                assert review.json() == last_runtime_result["payload"]
                assert_payload_schema(
                    review.json(),
                    REQUIRED_RUNTIME_ACTION_FIXTURES[5].response_schema,
                )

                progress = hermes_client.get("/v1/learners/learner_hermes_001/progress")
                assert progress.status_code == 200
                assert progress.json()["total_sessions"] == 1
                assert progress.status_code == last_runtime_result["status"]
                assert progress.json() == last_runtime_result["payload"]
                assert_payload_schema(
                    progress.json(),
                    REQUIRED_RUNTIME_ACTION_FIXTURES[7].response_schema,
                )

                installed = hermes_client.post(
                    "/v1/marketplace/org/org_hermes_001/install",
                    json={"skill_id": "mr_visit_jp"},
                )
                assert installed.status_code == 201

                org_started = hermes_client.post(
                    "/v1/sessions/start",
                    headers={"x-org-id": "org_hermes_001"},
                    json={"scenario_id": scenario_id, "learner_id": "learner_org_hermes_001"},
                )
                assert org_started.status_code == 200
                org_session_id = org_started.json()["session_id"]

                org_turn = hermes_client.post(
                    f"/v1/sessions/{org_session_id}/turn",
                    headers={"x-org-id": "org_hermes_001"},
                    json={"message": "Share one specific evidence point and ask a follow-up question."},
                )
                assert org_turn.status_code == 200

                org_finished = hermes_client.post(
                    f"/v1/sessions/{org_session_id}/finish",
                    headers={"x-org-id": "org_hermes_001"},
                )
                assert org_finished.status_code == 200

                org_reports = hermes_client.get(
                    "/v1/organizations/org_hermes_001/reports",
                    headers={
                        "x-org-id": "org_hermes_001",
                        "x-viewer-role": "supervisor",
                    },
                )
                assert org_reports.status_code == 200
                assert org_reports.json()["organization_id"] == "org_hermes_001"
                assert org_reports.status_code == last_runtime_result["status"]
                assert org_reports.json() == last_runtime_result["payload"]
                assert forwarded_headers[-1] == {
                    "x-request-id": forwarded_headers[-1]["x-request-id"],
                    "x-trace-id": forwarded_headers[-1]["x-trace-id"],
                    "x-org-id": "org_hermes_001",
                    "x-viewer-role": "supervisor",
                }
                assert_payload_schema(
                    org_reports.json(),
                    OPTIONAL_RUNTIME_ACTION_FIXTURES[2].response_schema,
                )

                gp_scenarios = hermes_client.get("/v1/skills/gp_visit_jp/scenarios")
                assert gp_scenarios.status_code == 200
                assert gp_scenarios.json()["domain_id"] == "gp_visit_jp"
                assert gp_scenarios.json()["scenario_count"] == 2
                gp_scenario_id = gp_scenarios.json()["scenarios"][0]["id"]

                gp_started = hermes_client.post(
                    "/v1/skills/gp_visit_jp/sessions/start",
                    json={"scenario_id": gp_scenario_id, "learner_id": "learner_gp_001"},
                )
                assert gp_started.status_code == 200
                assert gp_started.json()["scenario_id"] == gp_scenario_id
                assert gp_started.json()["experiment_context"]["profile_id"] == "gp_spike_baseline_v1"
                gp_session_id = gp_started.json()["session_id"]

                gp_turn = hermes_client.post(
                    f"/v1/skills/gp_visit_jp/sessions/{gp_session_id}/turn",
                    json={"message": "I understand this has been hard. What part of the daily routine makes adherence difficult?"},
                )
                assert gp_turn.status_code == 200
                assert gp_turn.json()["session_id"] == gp_session_id
                assert gp_turn.json()["persona_id"] is not None

                gp_finished = hermes_client.post(f"/v1/skills/gp_visit_jp/sessions/{gp_session_id}/finish")
                assert gp_finished.status_code == 200
                assert gp_finished.json()["review"]["meta"]["context"]["skill_id"] == "gp_visit_jp"
                assert gp_finished.json()["progress_snapshot"]["learner_id"] == "learner_gp_001"

    expected_forwarded_requests = {
        ("GET", OPTIONAL_RUNTIME_ACTION_FIXTURES[0].runtime_path()),
        ("GET", OPTIONAL_RUNTIME_ACTION_FIXTURES[0].runtime_path()),
        ("GET", REQUIRED_RUNTIME_ACTION_FIXTURES[0].runtime_path()),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[1].runtime_path()),
        ("GET", REQUIRED_RUNTIME_ACTION_FIXTURES[2].runtime_path(session_id=session_id)),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[3].runtime_path(session_id=session_id)),
        ("GET", REQUIRED_RUNTIME_ACTION_FIXTURES[6].runtime_path(session_id=session_id)),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[4].runtime_path(session_id=session_id)),
        ("GET", REQUIRED_RUNTIME_ACTION_FIXTURES[5].runtime_path(session_id=session_id)),
        ("GET", REQUIRED_RUNTIME_ACTION_FIXTURES[7].runtime_path(learner_id="learner_hermes_001")),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[1].runtime_path()),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[3].runtime_path(session_id=org_session_id)),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[4].runtime_path(session_id=org_session_id)),
        ("GET", OPTIONAL_RUNTIME_ACTION_FIXTURES[2].runtime_path(organization_id="org_hermes_001")),
        ("GET", REQUIRED_RUNTIME_ACTION_FIXTURES[0].runtime_path()),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[1].runtime_path()),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[3].runtime_path(session_id=gp_session_id)),
        ("POST", REQUIRED_RUNTIME_ACTION_FIXTURES[4].runtime_path(session_id=gp_session_id)),
    }
    assert expected_forwarded_requests.issubset(set(forwarded_requests))

    log_messages = [
        record.message
        for record in caplog.records
        if '"service_name": "hermes-orchestrator"' in record.message
    ]
    assert any("trace_hermes_chain_001" in message for message in log_messages)
    assert any(session_id in message for message in log_messages)
    assert any('"prompt_profile": "alpha_baseline_v1"' in message for message in log_messages)
    assert any('"learner_hash":' in message for message in log_messages)
    assert all("learner_hermes_001" not in message for message in log_messages)


def test_hermes_local_diagnostics_surface_runtime_target(
    hermes_runtime_apps: tuple[object, object, object],
) -> None:
    hermes_main, _runtime_main, _gp_runtime_main = hermes_runtime_apps

    with TestClient(hermes_main.app) as hermes_client:
        health = hermes_client.get("/healthz")
        assert health.status_code == 200
        health_payload = health.json()
        assert health_payload["default_skill_id"] == "mr_visit_jp"
        assert health_payload["skill_count"] == 2
        assert health_payload["runtime_api_base"] == "http://127.0.0.1:8100"

        diagnostics = hermes_client.get("/_local/diagnostics")
        assert diagnostics.status_code == 200
        payload = diagnostics.json()
        assert payload["service_name"] == "hermes-orchestrator"
        assert payload["default_skill_id"] == "mr_visit_jp"
        assert payload["skill_count"] == 2
        assert payload["runtime_api_base"] == "http://127.0.0.1:8100"
        assert payload["health_targets"]["runtime"] == "http://127.0.0.1:8100/healthz"
        assert payload["forward_trace_headers"] == [
            "x-request-id",
            "x-trace-id",
            "x-session-id",
            "x-turn-id",
        ]


def test_hermes_skill_validation_and_runtime_error_mapping(
    hermes_runtime_apps: tuple[object, object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hermes_main, _runtime_main, _gp_runtime_main = hermes_runtime_apps

    async def _boom(
        *,
        path: str,
        method: str = "GET",
        json_body=None,
        runtime_api_base: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        raise hermes_main.RuntimeProxyError("runtime down for contract test")

    monkeypatch.setattr(hermes_main, "proxy_runtime_request", _boom)

    with TestClient(hermes_main.app) as hermes_client:
        unknown_skill = hermes_client.get("/v1/skills/unknown/scenarios")
        assert unknown_skill.status_code == 404
        assert "Unknown skill_id" in unknown_skill.json()["detail"]

        upstream_failure = hermes_client.get("/v1/scenarios")
        assert upstream_failure.status_code == 502
        assert "runtime down for contract test" in upstream_failure.json()["detail"]
