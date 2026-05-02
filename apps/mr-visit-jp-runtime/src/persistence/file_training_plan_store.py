from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from persistence.file_store_support import (
    advisory_file_lock,
    atomic_write_text,
    load_json_object,
)
from persistence.interfaces import TrainingPlanStoreError


class FileTrainingPlanStore:
    """Simple file-backed training plan repository for Alpha runtime."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create(self, plan: dict[str, Any]) -> None:
        plan_id = str(plan.get("plan_id", ""))
        if not plan_id:
            raise TrainingPlanStoreError("plan_id is required")
        path = self._plan_path(plan_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    raise TrainingPlanStoreError(f"Training plan already exists: {plan_id}")
                with advisory_file_lock(path):
                    atomic_write_text(path, json.dumps(plan, ensure_ascii=False, indent=2))
            except TrainingPlanStoreError:
                raise
            except OSError as exc:
                raise TrainingPlanStoreError(
                    f"Failed to create training plan {plan_id} at {path}: {exc}"
                ) from exc

    def update(self, plan_id: str, payload: dict[str, Any]) -> None:
        path = self._plan_path(plan_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with advisory_file_lock(path):
                    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
            except OSError as exc:
                raise TrainingPlanStoreError(
                    f"Failed to update training plan {plan_id} at {path}: {exc}"
                ) from exc

    def get(self, plan_id: str) -> dict[str, Any] | None:
        path = self._plan_path(plan_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with advisory_file_lock(path):
                    if not path.exists():
                        return None
                    return load_json_object(
                        path,
                        entity_name="training_plan",
                        identifier_name="plan_id",
                        identifier_value=plan_id,
                        error_type=TrainingPlanStoreError,
                    )
            except TrainingPlanStoreError:
                raise
            except OSError as exc:
                raise TrainingPlanStoreError(
                    f"Failed to access training plan {plan_id} at {path}: {exc}"
                ) from exc

    def list_all(
        self,
        *,
        org_id: str | None = None,
        learner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        with self._lock:
            try:
                if not self._root_dir.exists():
                    return []
                for item in sorted(self._root_dir.iterdir()):
                    if not item.name.endswith(".json"):
                        continue
                    try:
                        data = load_json_object(
                            item,
                            entity_name="training_plan",
                            identifier_name="plan_id",
                            identifier_value=item.stem,
                            error_type=TrainingPlanStoreError,
                        )
                    except TrainingPlanStoreError:
                        continue
                    if data is None:
                        continue
                    if org_id and str(data.get("org_id", "")) != org_id:
                        continue
                    if learner_id:
                        assigned = data.get("assigned_learners", [])
                        if isinstance(assigned, list) and learner_id not in assigned:
                            continue
                    results.append(data)
            except OSError:
                return []
        return results

    def delete(self, plan_id: str) -> None:
        path = self._plan_path(plan_id)
        with self._lock:
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                raise TrainingPlanStoreError(
                    f"Failed to delete training plan {plan_id} at {path}: {exc}"
                ) from exc

    def _plan_path(self, plan_id: str) -> Path:
        if not plan_id or "/" in plan_id or "\\" in plan_id:
            raise TrainingPlanStoreError(f"Invalid plan_id: {plan_id}")
        return self._root_dir / f"{plan_id}.json"
