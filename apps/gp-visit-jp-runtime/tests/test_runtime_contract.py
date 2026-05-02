from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_FIXTURE_PATH = (
    REPO_ROOT
    / "apps"
    / "hermes-orchestrator"
    / "tests"
    / "runtime_contract_fixture.py"
)
RUNTIME_MAIN_PATH = REPO_ROOT / "apps" / "gp-visit-jp-runtime" / "src" / "main.py"


def _load_runtime_contract_fixture():
    alias = "shared_runtime_contract_fixture"
    spec = importlib.util.spec_from_file_location(alias, CONTRACT_FIXTURE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load runtime contract fixture: {CONTRACT_FIXTURE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _load_gp_runtime_main():
    alias = f"gp_runtime_main_contract_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(alias, RUNTIME_MAIN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load GP runtime module: {RUNTIME_MAIN_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def test_gp_runtime_matches_shared_runtime_contract() -> None:
    contract = _load_runtime_contract_fixture()
    runtime_main = _load_gp_runtime_main()
    runtime_main.app.state.sessions = {}
    runtime_main.app.state.events = {}
    runtime_main.app.state.progress = {}

    with TestClient(runtime_main.app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        contract.assert_runtime_health_payload(health.json())
        assert health.json()["domain_id"] == "gp_visit_jp"

        gates = client.get("/v1/evaluation-gates")
        assert gates.status_code == 200
        contract.assert_payload_schema(
            gates.json(),
            contract.OPTIONAL_RUNTIME_ACTION_FIXTURES[0].response_schema,
        )

        scenarios = client.get("/v1/scenarios")
        assert scenarios.status_code == 200
        scenarios_payload = scenarios.json()
        contract.assert_payload_schema(
            scenarios_payload,
            contract.REQUIRED_RUNTIME_ACTION_FIXTURES[0].response_schema,
        )
        assert scenarios_payload["domain_id"] == "gp_visit_jp"
        assert scenarios_payload["scenario_count"] == 2

        scenario_id = scenarios_payload["scenarios"][0]["id"]
        started = client.post(
            "/v1/sessions/start",
            json={"scenario_id": scenario_id, "learner_id": "learner_gp_contract_001"},
        )
        assert started.status_code == 200
        contract.assert_payload_schema(
            started.json(),
            contract.REQUIRED_RUNTIME_ACTION_FIXTURES[1].response_schema,
        )
        session_id = started.json()["session_id"]
        assert started.json()["experiment_context"]["profile_id"] == "gp_spike_baseline_v1"

        session = client.get(f"/v1/sessions/{session_id}")
        assert session.status_code == 200
        contract.assert_payload_schema(
            session.json(),
            contract.REQUIRED_RUNTIME_ACTION_FIXTURES[2].response_schema,
        )

        turn = client.post(
            f"/v1/sessions/{session_id}/turn",
            json={
                "message": (
                    "I understand this is difficult. What part of the daily routine makes "
                    "the medication or exercise plan hardest to keep?"
                )
            },
        )
        assert turn.status_code == 200
        contract.assert_payload_schema(
            turn.json(),
            contract.REQUIRED_RUNTIME_ACTION_FIXTURES[3].response_schema,
        )

        events = client.get(f"/v1/sessions/{session_id}/events")
        assert events.status_code == 200
        contract.assert_payload_schema(
            events.json(),
            contract.REQUIRED_RUNTIME_ACTION_FIXTURES[6].response_schema,
        )
        assert events.json()["event_count"] >= 2

        finished = client.post(f"/v1/sessions/{session_id}/finish")
        assert finished.status_code == 200
        contract.assert_payload_schema(
            finished.json(),
            contract.REQUIRED_RUNTIME_ACTION_FIXTURES[4].response_schema,
        )
        assert finished.json()["review"]["meta"]["context"]["skill_id"] == "gp_visit_jp"

        review = client.get(f"/v1/sessions/{session_id}/review")
        assert review.status_code == 200
        contract.assert_payload_schema(
            review.json(),
            contract.REQUIRED_RUNTIME_ACTION_FIXTURES[5].response_schema,
        )

        progress = client.get("/v1/learners/learner_gp_contract_001/progress")
        assert progress.status_code == 200
        contract.assert_payload_schema(
            progress.json(),
            contract.REQUIRED_RUNTIME_ACTION_FIXTURES[7].response_schema,
        )
        assert progress.json()["latest_recommendations"][0]["scenario_id"] != scenario_id
