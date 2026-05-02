"""
Tests for Skill Marketplace / Org Skill Installation lifecycle.

Three layers:
1. OrgSkillStore unit tests — direct file-backed store operations.
2. Marketplace API tests — Hermes marketplace endpoints via TestClient.
3. Installation routing tests — session start blocked for uninstalled skills.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from typing import Generator
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from org_skill_store import INSTALL_STATES, OrgSkillStore, OrgSkillStoreError

REPO_ROOT = Path(__file__).resolve().parents[3]
HERMES_SRC = REPO_ROOT / "apps" / "hermes-orchestrator" / "src"


def _load_hermes_app():
    original_sys_path = list(sys.path)
    hermes_src = str(HERMES_SRC)
    if hermes_src in sys.path:
        sys.path.remove(hermes_src)
    sys.path.insert(0, hermes_src)
    try:
        spec = importlib.util.spec_from_file_location(
            f"hermes_marketplace_main_{uuid4().hex}",
            HERMES_SRC / "main.py",
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load Hermes main.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module.app
    finally:
        sys.path[:] = original_sys_path


# =============================================================================
# Layer 1 — OrgSkillStore unit tests
# =============================================================================


@pytest.fixture
def store() -> Generator[OrgSkillStore, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield OrgSkillStore(data_dir=tmpdir)


class TestOrgSkillStore:
    def test_install_skill_creates_record(self, store: OrgSkillStore) -> None:
        record = store.install_skill("org_a", "mr_visit_jp", version="0.1.0")
        assert record["state"] == "installed"
        assert record["skill_id"] == "mr_visit_jp"
        assert record["org_id"] == "org_a"
        assert record["installed_version"] == "0.1.0"

    def test_get_installation_returns_none_for_missing(self, store: OrgSkillStore) -> None:
        assert store.get_installation("org_a", "nonexistent") is None

    def test_get_installation_returns_record(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        record = store.get_installation("org_a", "mr_visit_jp")
        assert record is not None
        assert record["state"] == "installed"

    def test_list_org_skills_empty_for_new_org(self, store: OrgSkillStore) -> None:
        assert store.list_org_skills("unknown_org") == {}

    def test_list_org_skills_returns_all(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        store.install_skill("org_a", "gp_visit_jp")
        skills = store.list_org_skills("org_a")
        assert len(skills) == 2

    def test_list_org_skills_state_filter(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        store.install_skill("org_a", "gp_visit_jp")
        store.set_state("org_a", "gp_visit_jp", "disabled")
        installed = store.list_org_skills("org_a", state_filter="installed")
        assert len(installed) == 1
        assert "mr_visit_jp" in installed
        disabled = store.list_org_skills("org_a", state_filter="disabled")
        assert len(disabled) == 1
        assert "gp_visit_jp" in disabled

    def test_set_state_changes_state(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        updated = store.set_state("org_a", "mr_visit_jp", "disabled", reason="testing")
        assert updated["state"] == "disabled"
        assert updated["reason"] == "testing"

    def test_set_state_invalid_state_raises(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        with pytest.raises(OrgSkillStoreError, match="Invalid installation state"):
            store.set_state("org_a", "mr_visit_jp", "invalid_state")

    def test_set_state_missing_skill_raises(self, store: OrgSkillStore) -> None:
        with pytest.raises(OrgSkillStoreError, match="not registered"):
            store.set_state("org_a", "nonexistent", "disabled")

    def test_remove_skill_removes_record(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        store.remove_skill("org_a", "mr_visit_jp")
        assert store.get_installation("org_a", "mr_visit_jp") is None

    def test_blocked_skill_cannot_be_installed(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        store.set_state("org_a", "mr_visit_jp", "blocked", reason="compliance")
        with pytest.raises(OrgSkillStoreError, match="blocked"):
            store.install_skill("org_a", "mr_visit_jp")

    def test_is_skill_available_true_when_installed(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        assert store.is_skill_available_for_learner("org_a", "mr_visit_jp") is True

    def test_is_skill_available_false_when_not_installed(self, store: OrgSkillStore) -> None:
        assert store.is_skill_available_for_learner("org_a", "mr_visit_jp") is False

    def test_is_skill_available_false_when_disabled(self, store: OrgSkillStore) -> None:
        store.install_skill("org_a", "mr_visit_jp")
        store.set_state("org_a", "mr_visit_jp", "disabled")
        assert store.is_skill_available_for_learner("org_a", "mr_visit_jp") is False

    def test_is_skill_available_true_without_org_id(self, store: OrgSkillStore) -> None:
        """In auth-disabled mode (no org context), always returns True."""
        assert store.is_skill_available_for_learner("", "any_skill") is True

    def test_org_isolation(self, store: OrgSkillStore) -> None:
        """Skills installed in org_A must not be visible in org_B."""
        store.install_skill("org_a", "mr_visit_jp")
        assert store.get_installation("org_b", "mr_visit_jp") is None
        assert store.is_skill_available_for_learner("org_b", "mr_visit_jp") is False


# =============================================================================
# Layer 2 — Marketplace API tests
# =============================================================================


@pytest.fixture
def hermes_client() -> Generator[TestClient, None, None]:
    """Hermes TestClient with mocked skill registry and isolated store."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"HERMES_DATA_DIR": tmpdir}, clear=False):
            app = _load_hermes_app()
            with TestClient(app) as client:
                yield client


class TestMarketplaceAPI:
    def test_list_marketplace_skills(self, hermes_client: TestClient) -> None:
        resp = hermes_client.get("/v1/marketplace")
        assert resp.status_code == 200
        data = resp.json()
        assert "skills" in data
        assert "items" in data
        assert len(data["items"]) >= 1
        # Each item should include installation state
        for item in data["items"]:
            assert "installation" in item
            assert item["installation"]["state"] in INSTALL_STATES

    def test_list_marketplace_with_org_header(self, hermes_client: TestClient) -> None:
        resp = hermes_client.get(
            "/v1/marketplace",
            headers={"X-Org-ID": "test_org"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Items should reflect org-specific installation state
        for item in data["items"]:
            assert item["installation"]["state"] == "available"

    def test_list_marketplace_includes_metadata(self, hermes_client: TestClient) -> None:
        resp = hermes_client.get("/v1/marketplace")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            # Only check the default skill (mr_visit_jp) which has marketplace metadata
            if item["id"] == "mr_visit_jp":
                assert item.get("marketplace") is not None
                assert item["marketplace"].get("title") is not None
                assert item["marketplace"].get("summary") is not None
                assert item["marketplace"].get("provider") == "COSI Platform"
                assert item["marketplace"].get("maturity") == "stable"

    def test_list_org_skills_empty(self, hermes_client: TestClient) -> None:
        resp = hermes_client.get("/v1/marketplace/org/new_org/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["org_id"] == "new_org"
        assert data["count"] == 0
        assert data["skills"] == {}

    def test_install_and_list_org_skill(self, hermes_client: TestClient) -> None:
        # Install
        resp = hermes_client.post(
            "/v1/marketplace/org/test_org/install",
            json={"skill_id": "mr_visit_jp", "version": "0.1.0"},
        )
        assert resp.status_code == 201
        record = resp.json()
        assert record["state"] == "installed"
        assert record["skill_id"] == "mr_visit_jp"

        # List should now include it
        resp = hermes_client.get("/v1/marketplace/org/test_org/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert "mr_visit_jp" in data["skills"]
        assert data["skills"]["mr_visit_jp"]["state"] == "installed"

    def test_set_skill_state(self, hermes_client: TestClient) -> None:
        # Install first
        hermes_client.post(
            "/v1/marketplace/org/test_org/install",
            json={"skill_id": "mr_visit_jp"},
        )
        # Disable
        resp = hermes_client.post(
            "/v1/marketplace/org/test_org/skills/mr_visit_jp/state",
            json={"state": "disabled", "reason": "maintenance"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "disabled"

        # Verify via list with filter
        resp = hermes_client.get(
            "/v1/marketplace/org/test_org/skills?state=disabled",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1

    def test_remove_org_skill(self, hermes_client: TestClient) -> None:
        hermes_client.post(
            "/v1/marketplace/org/test_org/install",
            json={"skill_id": "mr_visit_jp"},
        )
        resp = hermes_client.delete(
            "/v1/marketplace/org/test_org/skills/mr_visit_jp",
        )
        assert resp.status_code == 204

        # Verify gone
        resp = hermes_client.get("/v1/marketplace/org/test_org/skills")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_install_twice_same_skill_is_idempotent(self, hermes_client: TestClient) -> None:
        """Installing the same skill twice should work (upserts)."""
        hermes_client.post(
            "/v1/marketplace/org/test_org/install",
            json={"skill_id": "mr_visit_jp"},
        )
        resp = hermes_client.post(
            "/v1/marketplace/org/test_org/install",
            json={"skill_id": "mr_visit_jp"},
        )
        assert resp.status_code == 201

    def test_blocked_skill_install_returns_409(self, hermes_client: TestClient) -> None:
        # First block the skill
        hermes_client.post(
            "/v1/marketplace/org/test_org/install",
            json={"skill_id": "mr_visit_jp"},
        )
        hermes_client.post(
            "/v1/marketplace/org/test_org/skills/mr_visit_jp/state",
            json={"state": "blocked", "reason": "compliance"},
        )
        # Try to install again
        resp = hermes_client.post(
            "/v1/marketplace/org/test_org/install",
            json={"skill_id": "mr_visit_jp"},
        )
        assert resp.status_code == 409


# =============================================================================
# Layer 3 — Installation routing tests
# =============================================================================


class TestInstallationRouting:
    """Verify that Hermes blocks session start for uninstalled skills."""

    def test_session_start_blocked_for_uninstalled_skill(
        self, hermes_client: TestClient,
    ) -> None:
        """Learner with X-Org-ID must get 403 for uninstalled skill."""
        resp = hermes_client.post(
            "/v1/skills/mr_visit_jp/sessions/start",
            json={"scenario_id": "busy_doctor_short_visit", "learner_id": "learner_001"},
            headers={"X-Org-ID": "org_without_mr"},
        )
        assert resp.status_code == 403
        detail = resp.json().get("detail", "")
        assert "not installed" in detail.lower()

    def test_session_start_allowed_for_installed_skill(
        self, hermes_client: TestClient,
    ) -> None:
        """Learner with installed skill should be able to start."""
        # Install first
        hermes_client.post(
            "/v1/marketplace/org/org_with_mr/install",
            json={"skill_id": "mr_visit_jp"},
        )
        # Session start should pass the installation check and reach the
        # runtime proxy, which will fail with 502 (no runtime) instead of 403.
        resp = hermes_client.post(
            "/v1/skills/mr_visit_jp/sessions/start",
            json={"scenario_id": "busy_doctor_short_visit", "learner_id": "learner_001"},
            headers={"X-Org-ID": "org_with_mr"},
        )
        # Should not be 403 — either 200 (if runtime available) or 502 (no runtime)
        assert resp.status_code != 403, "Installation check should have passed"

    def test_session_start_allowed_without_org_id(
        self, hermes_client: TestClient,
    ) -> None:
        """Without X-Org-ID (demo mode), session start should be allowed."""
        resp = hermes_client.post(
            "/v1/skills/mr_visit_jp/sessions/start",
            json={"scenario_id": "busy_doctor_short_visit", "learner_id": "learner_001"},
        )
        # Should not be 403
        assert resp.status_code != 403

    def test_unscoped_session_start_blocked_after_install_check(
        self, hermes_client: TestClient,
    ) -> None:
        """Unscoped session start is routed to default skill — must also check installation."""
        resp = hermes_client.post(
            "/v1/sessions/start",
            json={"scenario_id": "busy_doctor_short_visit", "learner_id": "learner_001"},
            headers={"X-Org-ID": "org_without_any_skill"},
        )
        assert resp.status_code == 403

    def test_local_org_auto_installs_missing_skill_in_development(
        self, hermes_client: TestClient,
    ) -> None:
        """Local org should auto-install missing skills in development mode."""
        resp = hermes_client.post(
            "/v1/skills/mr_visit_jp/sessions/start",
            json={"scenario_id": "busy_doctor_short_visit", "learner_id": "learner_001"},
            headers={"X-Org-ID": "local"},
        )
        assert resp.status_code != 403

        skills_resp = hermes_client.get("/v1/marketplace/org/local/skills")
        assert skills_resp.status_code == 200
        skills = skills_resp.json()["skills"]
        assert "mr_visit_jp" in skills
        assert skills["mr_visit_jp"]["state"] == "installed"

    def test_local_org_auto_install_can_be_disabled(
        self, hermes_client: TestClient,
    ) -> None:
        """Auto-install guard should be disableable via env var."""
        hermes_client.delete("/v1/marketplace/org/local/skills/mr_visit_jp")
        with patch.dict(os.environ, {"HERMES_LOCAL_AUTO_INSTALL_SKILLS": "false"}, clear=False):
            resp = hermes_client.post(
                "/v1/skills/mr_visit_jp/sessions/start",
                json={"scenario_id": "busy_doctor_short_visit", "learner_id": "learner_001"},
                headers={"X-Org-ID": "local"},
            )
        assert resp.status_code == 403
