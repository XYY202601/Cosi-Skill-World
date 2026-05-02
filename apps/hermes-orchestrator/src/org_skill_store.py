"""
Organization-level skill installation state.

Tracks which skills are installed, disabled, or blocked per organization.
Allows Hermes to check installation state during routing and provides
CRUD for organization admins to manage their skill portfolio.

Installation states:
  available         — skill is registered but not yet installed for this org
  installed         — skill is installed and enabled for this org
  disabled          — skill was installed but is temporarily disabled
  upgrade_available — a newer version is available (compared to installed_version)
  blocked           — skill cannot be installed for this org (compliance/regional)

File layout (under HERMES_DATA_DIR / "org-skills"):
  {org_id}.json  — JSON object mapping skill_id -> installation record
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any


INSTALL_STATES = frozenset({
    "available",
    "installed",
    "disabled",
    "upgrade_available",
    "blocked",
})

HERMES_DATA_DIR_DEFAULT = "data/org-skills"


class OrgSkillStoreError(RuntimeError):
    """Raised when an org skill operation fails."""


class OrgSkillStore:
    """File-based organization skill installation state store.

    Each org has its own JSON file containing a dict of skill_id -> record.
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self._root = Path(data_dir or os.getenv(
            "HERMES_DATA_DIR", HERMES_DATA_DIR_DEFAULT,
        ))
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _org_path(self, org_id: str) -> Path:
        return self._root / f"{org_id}.json"

    def _load_org(self, org_id: str) -> dict[str, Any]:
        path = self._org_path(org_id)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save_org(self, org_id: str, data: dict[str, Any]) -> None:
        path = self._org_path(org_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_installation(
        self, org_id: str, skill_id: str,
    ) -> dict[str, Any] | None:
        """Return the installation record for a single skill in an org."""
        with self._lock:
            org_data = self._load_org(org_id)
            return org_data.get(skill_id)

    def list_org_skills(
        self, org_id: str, *,
        state_filter: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        """List all skill installation records for an org, optionally filtered."""
        with self._lock:
            org_data = self._load_org(org_id)
            if state_filter:
                return {
                    skill_id: rec
                    for skill_id, rec in org_data.items()
                    if rec.get("state") == state_filter
                }
            return dict(org_data)

    def install_skill(
        self, org_id: str, skill_id: str, *,
        version: str = "",
        installed_by: str = "",
    ) -> dict[str, Any]:
        """Install a skill for an org (state -> 'installed')."""
        now = _now_iso()
        record: dict[str, Any] = {
            "skill_id": skill_id,
            "org_id": org_id,
            "state": "installed",
            "installed_version": version,
            "installed_at": now,
            "installed_by": installed_by,
            "updated_at": now,
            "reason": "",
        }
        with self._lock:
            org_data = self._load_org(org_id)
            existing = org_data.get(skill_id)
            if existing and existing.get("state") == "blocked":
                raise OrgSkillStoreError(
                    f"Skill `{skill_id}` is blocked for org `{org_id}`"
                )
            org_data[skill_id] = record
            self._save_org(org_id, org_data)
        return record

    def set_state(
        self, org_id: str, skill_id: str, new_state: str, *,
        reason: str = "",
    ) -> dict[str, Any]:
        """Change installation state for a skill."""
        if new_state not in INSTALL_STATES:
            raise OrgSkillStoreError(
                f"Invalid installation state: `{new_state}`. "
                f"Must be one of: {sorted(INSTALL_STATES)}"
            )
        now = _now_iso()
        with self._lock:
            org_data = self._load_org(org_id)
            existing = org_data.get(skill_id)
            if not existing:
                raise OrgSkillStoreError(
                    f"Skill `{skill_id}` is not registered for org `{org_id}`"
                )
            existing["state"] = new_state
            existing["updated_at"] = now
            existing["reason"] = reason
            org_data[skill_id] = existing
            self._save_org(org_id, org_data)
        return existing

    def remove_skill(self, org_id: str, skill_id: str) -> None:
        """Remove a skill record entirely from an org's state."""
        with self._lock:
            org_data = self._load_org(org_id)
            org_data.pop(skill_id, None)
            self._save_org(org_id, org_data)

    def is_skill_available_for_learner(
        self, org_id: str, skill_id: str,
    ) -> bool:
        """Check whether a learner in an org can use a skill.

        In auth-disabled mode (no org context), returns True.
        Returns True if the skill is installed, False otherwise.
        """
        if not org_id:
            return True  # auth-disabled or demo mode
        record = self.get_installation(org_id, skill_id)
        if record is None:
            return False  # not installed for this org
        return record.get("state") == "installed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
