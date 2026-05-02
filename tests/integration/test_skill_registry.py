from __future__ import annotations

import copy
from pathlib import Path

import yaml
import pytest

from skill_registry import (
    SkillRegistryError,
    load_skill_manifest,
    load_skill_registry,
    resolve_runtime_api_base,
)


def test_skill_registry_loads_domain_manifest_and_default_skill() -> None:
    registry = load_skill_registry()

    assert registry.list_skill_ids() == ["gp_visit_jp", "mr_visit_jp"]
    default_skill = registry.default_skill()
    assert default_skill.id == "mr_visit_jp"
    assert default_skill.runtime.base_url_env == "MR_VISIT_JP_RUNTIME_BASE"

    action = default_skill.action("send_turn")
    assert action.method == "POST"
    assert action.build_runtime_path(
        base_path=default_skill.runtime.base_path,
        path_values={"session_id": "sess_123"},
    ) == "/v1/sessions/sess_123/turn"


def test_skill_registry_lists_capabilities_and_actions_in_summary() -> None:
    registry = load_skill_registry()

    summaries = {item["id"]: item for item in registry.list_summaries()}
    summary = summaries["mr_visit_jp"]
    capability_ids = [item["id"] for item in summary["capabilities"]]
    action_ids = [item["id"] for item in summary["actions"]]

    assert summary["default_for_unscoped_routes"] is True
    assert capability_ids == [
        "scenario_catalog",
        "practice_session",
        "review",
        "progress",
        "organization_reporting",
    ]
    assert "get_session_events" in action_ids
    assert "get_progress_snapshot" in action_ids
    assert "get_organization_reports" in action_ids


def test_gp_spike_manifest_is_enabled_and_visible_in_registry() -> None:
    spike_manifest_path = (
        Path(__file__).resolve().parents[2]
        / "domains"
        / "gp_visit_jp"
        / "manifests"
        / "skill.yaml"
    )

    manifest = load_skill_manifest(spike_manifest_path)
    registry = load_skill_registry()

    assert manifest.id == "gp_visit_jp"
    assert manifest.registration_enabled is True
    assert manifest.runtime.base_url_env == "GP_VISIT_JP_RUNTIME_BASE"
    assert manifest.action("send_turn").path == "/sessions/{session_id}/turn"
    assert "gp_visit_jp" in registry.list_skill_ids()


def test_skill_registry_rejects_path_param_mismatch(tmp_path: Path) -> None:
    source_manifest = (
        Path(__file__).resolve().parents[2]
        / "domains"
        / "mr_visit_jp"
        / "manifests"
        / "skill.yaml"
    )
    payload = copy.deepcopy(yaml.safe_load(source_manifest.read_text(encoding="utf-8")))
    target_action = next(
        action for action in payload["actions"] if action["id"] == "get_session"
    )
    target_action["path_params"] = ["learner_id"]

    bad_manifest = tmp_path / "skill.yaml"
    bad_manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(SkillRegistryError, match="path params must match placeholders"):
        load_skill_registry([bad_manifest])


def test_skill_registry_accepts_optional_runtime_contract_actions(tmp_path: Path) -> None:
    source_manifest = (
        Path(__file__).resolve().parents[2]
        / "domains"
        / "mr_visit_jp"
        / "manifests"
        / "skill.yaml"
    )
    payload = copy.deepcopy(yaml.safe_load(source_manifest.read_text(encoding="utf-8")))
    capability_ids = {item["id"] for item in payload["capabilities"]}
    action_ids = {item["id"] for item in payload["actions"]}

    if "curriculum" not in capability_ids:
        payload["capabilities"].append(
            {
                "id": "curriculum",
                "name": "Curriculum",
                "description": "Expose curriculum structure for this skill.",
                "actions": ["get_curriculum"],
            }
        )
    if "organization_reporting" not in capability_ids:
        payload["capabilities"].append(
            {
                "id": "organization_reporting",
                "name": "Organization Reporting",
                "description": "Expose supervisor-facing aggregate reports for this skill.",
                "actions": ["get_organization_reports"],
            }
        )

    if "get_curriculum" not in action_ids:
        payload["actions"].append(
            {
                "id": "get_curriculum",
                "capability": "curriculum",
                "method": "GET",
                "path": "/curriculum",
                "expose": ["root", "skill"],
                "description": "Read curriculum structure for this skill.",
            }
        )
    if "get_organization_reports" not in action_ids:
        payload["actions"].append(
            {
                "id": "get_organization_reports",
                "capability": "organization_reporting",
                "method": "GET",
                "path": "/organizations/{organization_id}/reports",
                "path_params": ["organization_id"],
                "expose": ["root", "skill"],
                "description": "Read organization-level reports for this skill.",
            }
        )

    manifest_path = tmp_path / "skill.yaml"
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    manifest = load_skill_manifest(manifest_path)

    assert manifest.action("get_curriculum").path == "/curriculum"
    assert manifest.action("get_organization_reports").path == "/organizations/{organization_id}/reports"


def test_resolve_runtime_api_base_requires_skill_specific_env_for_non_default_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = load_skill_registry()
    gp_runtime = registry.require("gp_visit_jp").runtime

    monkeypatch.delenv("GP_VISIT_JP_RUNTIME_BASE", raising=False)
    monkeypatch.delenv("RUNTIME_API_BASE", raising=False)

    with pytest.raises(SkillRegistryError, match="Missing runtime base URL"):
        resolve_runtime_api_base(gp_runtime)


def test_resolve_runtime_api_base_keeps_default_runtime_legacy_fallback() -> None:
    registry = load_skill_registry()
    mr_runtime = registry.default_skill().runtime

    assert resolve_runtime_api_base(mr_runtime) == "http://127.0.0.1:8100"
