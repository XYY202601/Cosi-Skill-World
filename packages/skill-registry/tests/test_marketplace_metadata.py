"""
Tests for skill manifest marketplace metadata parsing and validation.

Verifies that marketplace fields are correctly parsed from YAML manifest,
included in summaries, and that backward compatibility is preserved when
marketplace section is omitted.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from skill_registry.registry import load_skill_manifest, load_skill_registry


# Minimal valid manifest without marketplace section (backward compatibility).
# Keep this aligned with skill_manifest.schema.json so these tests exercise
# marketplace parsing, not unrelated runtime-contract validation.
MINIMAL_MANIFEST = {
    "id": "test_skill",
    "version": "0.1.0",
    "name": "Test Skill",
    "routing": {"default_for_unscoped_routes": False},
    "runtime": {
        "app": "test-runtime",
        "base_path": "/v1",
        "health_path": "/healthz",
        "base_url_env": "TEST_RUNTIME_BASE",
    },
    "capabilities": [
        {
            "id": "scenario_catalog",
            "name": "Scenario Catalog",
            "description": "Test catalog",
            "actions": [
                "list_scenarios",
                "get_evaluation_gates",
                "start_session",
                "get_session",
                "get_progress_snapshot",
            ],
        },
    ],
    "actions": [
        {
            "id": "list_scenarios",
            "capability": "scenario_catalog",
            "method": "GET",
            "path": "/scenarios",
            "expose": ["root"],
            "description": "List scenarios.",
        },
        {
            "id": "get_evaluation_gates",
            "capability": "scenario_catalog",
            "method": "GET",
            "path": "/evaluation-gates",
            "expose": ["root"],
            "description": "Read evaluation gate status.",
        },
        {
            "id": "start_session",
            "capability": "scenario_catalog",
            "method": "POST",
            "path": "/sessions/start",
            "expose": ["root"],
            "description": "Start a new session.",
        },
        {
            "id": "get_session",
            "capability": "scenario_catalog",
            "method": "GET",
            "path": "/sessions/{session_id}",
            "path_params": ["session_id"],
            "expose": ["root"],
            "description": "Read current session state.",
        },
        {
            "id": "get_progress_snapshot",
            "capability": "scenario_catalog",
            "method": "GET",
            "path": "/learners/{learner_id}/progress",
            "path_params": ["learner_id"],
            "expose": ["root"],
            "description": "Read learner progress.",
        },
    ],
    "subskills": ["test_subskill"],
}


def _write_manifest(tmpdir: str | Path, overrides: dict | None = None) -> Path:
    """Write a manifest YAML file and return its path."""
    import yaml

    target_dir = Path(tmpdir)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(MINIMAL_MANIFEST)
    if overrides:
        payload.update(overrides)
    path = target_dir / "skill.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(payload, f, default_flow_style=False)
    return path


class TestMarketplaceMetadataParsing:
    def test_marketplace_omitted_defaults_to_empty(self) -> None:
        """Backward compatibility: no marketplace section produces empty metadata."""
        with TemporaryDirectory() as tmpdir:
            path = _write_manifest(tmpdir)
            manifest = load_skill_manifest(path)
            assert manifest.marketplace.title == ""
            assert manifest.marketplace.summary == ""
            assert manifest.marketplace.provider == ""

    def test_marketplace_full_parsing(self) -> None:
        """All marketplace fields are parsed correctly."""
        with TemporaryDirectory() as tmpdir:
            path = _write_manifest(tmpdir, {
                "marketplace": {
                    "title": "Test Skill Title",
                    "summary": "A test skill for unit tests.",
                    "provider": "Test Provider",
                    "locales": ["en", "ja"],
                    "modality": "text",
                    "maturity": "beta",
                    "compatibility": {"min_runtime_version": "0.1.0"},
                    "privacy": {"data_notes": "No personal data collected."},
                },
            })
            manifest = load_skill_manifest(path)
            mk = manifest.marketplace
            assert mk.title == "Test Skill Title"
            assert mk.summary == "A test skill for unit tests."
            assert mk.provider == "Test Provider"
            assert mk.locales == ("en", "ja")
            assert mk.modality == "text"
            assert mk.maturity == "beta"
            assert mk.min_runtime_version == "0.1.0"
            assert mk.data_notes == "No personal data collected."

    def test_marketplace_partial_parsing(self) -> None:
        """Partial marketplace section fills missing fields with defaults."""
        with TemporaryDirectory() as tmpdir:
            path = _write_manifest(tmpdir, {
                "marketplace": {
                    "title": "Partial Skill",
                    "summary": "Only title and summary provided.",
                },
            })
            manifest = load_skill_manifest(path)
            mk = manifest.marketplace
            assert mk.title == "Partial Skill"
            assert mk.summary == "Only title and summary provided."
            assert mk.provider == ""
            assert mk.locales == ()
            assert mk.modality == ""
            assert mk.maturity == ""

    def test_marketplace_in_summary(self) -> None:
        """Marketplace metadata appears in to_summary() output."""
        with TemporaryDirectory() as tmpdir:
            path = _write_manifest(tmpdir, {
                "marketplace": {
                    "title": "Summary Test",
                    "summary": "Check summary output.",
                    "provider": "COSI",
                },
            })
            manifest = load_skill_manifest(path)
            summary = manifest.to_summary()
            assert summary["marketplace"] is not None
            assert summary["marketplace"]["title"] == "Summary Test"
            assert summary["marketplace"]["summary"] == "Check summary output."

    def test_marketplace_none_in_summary_when_empty(self) -> None:
        """to_summary returns null for marketplace when title is empty."""
        with TemporaryDirectory() as tmpdir:
            path = _write_manifest(tmpdir)
            manifest = load_skill_manifest(path)
            summary = manifest.to_summary()
            assert summary["marketplace"] is None


class TestMarketplaceWithRegistry:
    def test_registry_summaries_include_marketplace(self) -> None:
        """Registry list_summaries() includes marketplace for skills that have it."""
        with TemporaryDirectory() as tmpdir:
            path1 = _write_manifest(tmpdir, {
                "id": "skill_a",
                "marketplace": {"title": "Skill A", "summary": "First skill."},
            })
            path2 = _write_manifest(Path(tmpdir) / "sub", {
                "id": "skill_b",
            })

            registry = load_skill_registry([path1, path2])
            summaries = registry.list_summaries()
            summary_map = {s["id"]: s for s in summaries}

            assert summary_map["skill_a"]["marketplace"] is not None
            assert summary_map["skill_a"]["marketplace"]["title"] == "Skill A"
            assert summary_map["skill_b"]["marketplace"] is None


class TestManifestValidation:
    def test_existing_manifests_still_validate(self) -> None:
        """The real mr_visit_jp and gp_visit_jp manifests still pass schema validation."""
        registry = load_skill_registry()
        manifests = registry.list_summaries()
        ids = {m["id"] for m in manifests}
        assert "mr_visit_jp" in ids
        assert "gp_visit_jp" in ids

    def test_marketplace_fields_are_validated(self) -> None:
        """Invalid marketplace fields should fail schema validation."""
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "skill.yaml"
            # bad modality value
            bad = deepcopy(MINIMAL_MANIFEST)
            bad["marketplace"] = {"modality": "hologram"}
            import yaml
            with path.open("w", encoding="utf-8") as f:
                yaml.dump(bad, f, default_flow_style=False)

            from skill_registry.registry import SkillRegistryError
            with pytest.raises(SkillRegistryError, match="modality"):
                load_skill_manifest(path)
