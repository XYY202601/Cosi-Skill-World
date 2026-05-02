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
from persistence.interfaces import ProgressStoreError


class FileProgressStore:
    """Simple file-backed learner progress repository for Alpha runtime."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def upsert(self, learner_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        path = self._progress_path(learner_id, org_id=org_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with advisory_file_lock(path):
                    self._write_json(path, payload, learner_id=learner_id)
            except OSError as exc:
                raise ProgressStoreError(
                    f"Failed to access progress payload for learner_id={learner_id} at {path}: {exc}"
                ) from exc

    def get(self, learner_id: str, *, org_id: str | None = None) -> dict[str, Any] | None:
        path = self._progress_path(learner_id, org_id=org_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with advisory_file_lock(path):
                    if not path.exists():
                        return None
                    return load_json_object(
                        path,
                        entity_name="progress",
                        identifier_name="learner_id",
                        identifier_value=learner_id,
                        error_type=ProgressStoreError,
                    )
            except ProgressStoreError:
                raise
            except OSError as exc:
                raise ProgressStoreError(
                    f"Failed to access progress payload for learner_id={learner_id} at {path}: {exc}"
                ) from exc

    def _progress_path(self, learner_id: str, *, org_id: str | None = None) -> Path:
        if not learner_id or "/" in learner_id or "\\" in learner_id:
            raise ProgressStoreError(f"Invalid learner_id: {learner_id}")
        base = self._root_dir
        if org_id:
            base = base / org_id
        return base / f"{learner_id}.json"

    def _write_json(self, path: Path, payload: dict[str, Any], *, learner_id: str) -> None:
        try:
            atomic_write_text(
                path,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        except OSError as exc:
            raise ProgressStoreError(
                f"Failed to persist progress payload for learner_id={learner_id} at {path}: {exc}"
            ) from exc
