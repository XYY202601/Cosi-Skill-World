from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from persistence.file_store_support import (
    LOGGER,
    advisory_file_lock,
    atomic_write_text,
    load_json_object,
)
from persistence.interfaces import SessionStoreConflictError, SessionStoreError


class FileSessionStore:
    """Simple file-backed session repository for Alpha runtime."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create(self, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        path = self._session_path(session_id, org_id=org_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with advisory_file_lock(path):
                    if path.exists():
                        raise SessionStoreConflictError(f"Session already exists: {session_id}")
                    self._write_json(path, payload, session_id=session_id)
            except SessionStoreError:
                raise
            except OSError as exc:
                raise SessionStoreError(
                    f"Failed to access session payload for session_id={session_id} at {path}: {exc}"
                ) from exc

    def upsert(self, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        path = self._session_path(session_id, org_id=org_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with advisory_file_lock(path):
                    self._write_json(path, payload, session_id=session_id)
            except OSError as exc:
                raise SessionStoreError(
                    f"Failed to access session payload for session_id={session_id} at {path}: {exc}"
                ) from exc

    def get(self, session_id: str, *, org_id: str | None = None) -> dict[str, Any] | None:
        path = self._session_path(session_id, org_id=org_id)
        with self._lock:
            try:
                with advisory_file_lock(path):
                    if not path.exists():
                        return None
                    return load_json_object(
                        path,
                        entity_name="session",
                        identifier_name="session_id",
                        identifier_value=session_id,
                        error_type=SessionStoreError,
                    )
            except SessionStoreError:
                raise
            except OSError as exc:
                raise SessionStoreError(
                    f"Failed to access session payload for session_id={session_id} at {path}: {exc}"
                ) from exc

    def list_all(self, *, org_id: str | None = None) -> list[dict[str, Any]]:
        target_dir = self._root_dir
        if org_id:
            target_dir = self._root_dir / org_id
            if not target_dir.exists():
                return []
        
        with self._lock:
            payloads: list[dict[str, Any]] = []
            for path in sorted(target_dir.glob("*.json")):
                try:
                    with advisory_file_lock(path):
                        payloads.append(
                            load_json_object(
                                path,
                                entity_name="session",
                                identifier_name="session_id",
                                identifier_value=path.stem,
                                error_type=SessionStoreError,
                            )
                        )
                except SessionStoreError as exc:
                    LOGGER.warning("Skipping unreadable session payload during list_all: %s", exc)
                    continue
                except OSError as exc:
                    raise SessionStoreError(
                        f"Failed to access session payload for session_id={path.stem} at {path}: {exc}"
                    ) from exc
            return payloads

    def _session_path(self, session_id: str, *, org_id: str | None = None) -> Path:
        if not session_id or "/" in session_id or "\\" in session_id:
            raise SessionStoreError(f"Invalid session_id: {session_id}")
        
        base = self._root_dir
        if org_id:
            base = base / org_id
        return base / f"{session_id}.json"

    def _write_json(self, path: Path, payload: dict[str, Any], *, session_id: str) -> None:
        try:
            atomic_write_text(
                path,
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        except OSError as exc:
            raise SessionStoreError(
                f"Failed to persist session payload for session_id={session_id} at {path}: {exc}"
            ) from exc
