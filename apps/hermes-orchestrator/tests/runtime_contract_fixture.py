from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMAS_DIR = REPO_ROOT / "packages" / "shared-schemas" / "schemas"
DEFAULT_RUNTIME_BASE_PATH = "/v1"
DEFAULT_RUNTIME_HEALTH_PATH = "/healthz"
REQUIRED_RUNTIME_ACTION_IDS = (
    "list_scenarios",
    "start_session",
    "get_session",
    "send_turn",
    "finish_session",
    "get_review",
    "get_session_events",
    "get_progress_snapshot",
)
OPTIONAL_RUNTIME_ACTION_IDS = (
    "get_evaluation_gates",
    "get_curriculum",
    "get_organization_reports",
)


@dataclass(frozen=True)
class RuntimeContractActionFixture:
    action_id: str
    method: str
    path: str
    path_params: tuple[str, ...] = ()
    response_schema: str | None = None
    expose: tuple[str, ...] = ("root", "skill")

    def runtime_path(self, **path_values: str) -> str:
        return f"{DEFAULT_RUNTIME_BASE_PATH}{self.path}".format(**path_values)

    def hermes_root_path(self, **path_values: str) -> str:
        return self.runtime_path(**path_values)

    def hermes_skill_path(self, skill_id: str, **path_values: str) -> str:
        return f"{DEFAULT_RUNTIME_BASE_PATH}/skills/{skill_id}{self.path}".format(**path_values)


REQUIRED_RUNTIME_ACTION_FIXTURES = (
    RuntimeContractActionFixture(
        action_id="list_scenarios",
        method="GET",
        path="/scenarios",
        response_schema="runtime_scenario_list_response.schema.json",
    ),
    RuntimeContractActionFixture(
        action_id="start_session",
        method="POST",
        path="/sessions/start",
        response_schema="runtime_session_start_response.schema.json",
    ),
    RuntimeContractActionFixture(
        action_id="get_session",
        method="GET",
        path="/sessions/{session_id}",
        path_params=("session_id",),
        response_schema="runtime_session_response.schema.json",
    ),
    RuntimeContractActionFixture(
        action_id="send_turn",
        method="POST",
        path="/sessions/{session_id}/turn",
        path_params=("session_id",),
        response_schema="runtime_send_turn_response.schema.json",
    ),
    RuntimeContractActionFixture(
        action_id="finish_session",
        method="POST",
        path="/sessions/{session_id}/finish",
        path_params=("session_id",),
        response_schema="runtime_finish_session_response.schema.json",
    ),
    RuntimeContractActionFixture(
        action_id="get_review",
        method="GET",
        path="/sessions/{session_id}/review",
        path_params=("session_id",),
        response_schema="runtime_review_response.schema.json",
    ),
    RuntimeContractActionFixture(
        action_id="get_session_events",
        method="GET",
        path="/sessions/{session_id}/events",
        path_params=("session_id",),
        response_schema="runtime_session_events_response.schema.json",
    ),
    RuntimeContractActionFixture(
        action_id="get_progress_snapshot",
        method="GET",
        path="/learners/{learner_id}/progress",
        path_params=("learner_id",),
        response_schema="runtime_progress_snapshot_response.schema.json",
    ),
)

OPTIONAL_RUNTIME_ACTION_FIXTURES = (
    RuntimeContractActionFixture(
        action_id="get_evaluation_gates",
        method="GET",
        path="/evaluation-gates",
        response_schema="runtime_evaluation_gates_response.schema.json",
    ),
    RuntimeContractActionFixture(
        action_id="get_curriculum",
        method="GET",
        path="/curriculum",
    ),
    RuntimeContractActionFixture(
        action_id="get_organization_reports",
        method="GET",
        path="/organizations/{organization_id}/reports",
        path_params=("organization_id",),
        response_schema="runtime_organization_reports_response.schema.json",
    ),
)


def _load_schema(schema_name: str) -> dict[str, Any]:
    with (SCHEMAS_DIR / schema_name).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict)
    return payload


def assert_payload_schema(payload: object, schema_name: str) -> None:
    schema = _load_schema(schema_name)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    assert not errors, errors[0].message


def assert_runtime_health_payload(payload: object) -> None:
    assert_payload_schema(payload, "runtime_health_response.schema.json")


def assert_skill_summary_supports_required_runtime_contract(summary: dict[str, Any]) -> None:
    runtime = summary["runtime"]
    assert runtime["base_path"] == DEFAULT_RUNTIME_BASE_PATH
    assert runtime["health_path"] == DEFAULT_RUNTIME_HEALTH_PATH
    action_map = {item["id"]: item for item in summary["actions"]}

    missing_actions = sorted(set(REQUIRED_RUNTIME_ACTION_IDS) - set(action_map))
    assert not missing_actions, missing_actions

    for fixture in REQUIRED_RUNTIME_ACTION_FIXTURES:
        action = action_map[fixture.action_id]
        assert action["method"] == fixture.method
        assert action["path"] == fixture.path
        assert tuple(action.get("path_params", [])) == fixture.path_params
        assert tuple(action["expose"]) == fixture.expose
