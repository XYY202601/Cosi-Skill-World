from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from persistence.file_store_support import (
    advisory_file_lock,
    atomic_write_text,
    load_jsonl_objects,
)
from persistence.interfaces import EventStoreError
from session_events import normalize_session_event_payload, normalize_session_event_payloads


class FileEventStore:
    """File-backed append-only event store for Alpha runtime."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def append(self, session_id: str, event: dict[str, Any], *, org_id: str | None = None) -> None:
        path = self._events_path(session_id, org_id=org_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with advisory_file_lock(path):
                    payloads = self._read_events_locked(path, session_id=session_id)
                    next_seq = self._next_seq(payloads)
                    normalized = self._normalize_event_for_write(
                        event,
                        session_id=session_id,
                        path=path,
                        inferred_seq=next_seq,
                    )
                    payloads.append(normalized)
                    self._write_events_locked(path, payloads, session_id=session_id)
            except EventStoreError:
                raise
            except OSError as exc:
                raise EventStoreError(
                    f"Failed to access event payload for session_id={session_id} at {path}: {exc}"
                ) from exc

    def replace(self, session_id: str, events: list[dict[str, Any]], *, org_id: str | None = None) -> None:
        path = self._events_path(session_id, org_id=org_id)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with advisory_file_lock(path):
                    normalized_events = self._normalize_events_for_write(
                        events,
                        session_id=session_id,
                        path=path,
                    )
                    self._write_events_locked(path, normalized_events, session_id=session_id)
            except EventStoreError:
                raise
            except OSError as exc:
                raise EventStoreError(
                    f"Failed to access event payload for session_id={session_id} at {path}: {exc}"
                ) from exc

    def list_events(self, session_id: str, *, org_id: str | None = None) -> list[dict[str, Any]]:
        path = self._events_path(session_id, org_id=org_id)
        with self._lock:
            try:
                with advisory_file_lock(path):
                    return self._read_events_locked(path, session_id=session_id)
            except EventStoreError:
                raise
            except OSError as exc:
                raise EventStoreError(
                    f"Failed to access event payload for session_id={session_id} at {path}: {exc}"
                ) from exc

    def _read_events_locked(self, path: Path, *, session_id: str) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        payloads = load_jsonl_objects(
            path,
            entity_name="event",
            identifier_name="session_id",
            identifier_value=session_id,
            error_type=EventStoreError,
        )
        try:
            return normalize_session_event_payloads(
                payloads,
                fallback_session_id=session_id,
            )
        except ValueError as exc:
            raise EventStoreError(
                f"Corrupted event payload for session_id={session_id} at {path}: {exc}"
            ) from exc

    def _normalize_event_for_write(
        self,
        event: dict[str, Any],
        *,
        session_id: str,
        path: Path,
        inferred_seq: int,
    ) -> dict[str, Any]:
        try:
            return normalize_session_event_payload(
                event,
                fallback_session_id=session_id,
                inferred_seq=inferred_seq,
            )
        except ValueError as exc:
            raise EventStoreError(
                f"Invalid event payload for session_id={session_id} at {path}: {exc}"
            ) from exc

    def _normalize_events_for_write(
        self,
        events: list[dict[str, Any]],
        *,
        session_id: str,
        path: Path,
    ) -> list[dict[str, Any]]:
        try:
            return normalize_session_event_payloads(
                events,
                fallback_session_id=session_id,
            )
        except ValueError as exc:
            raise EventStoreError(
                f"Invalid event payload for session_id={session_id} at {path}: {exc}"
            ) from exc

    def _write_events_locked(
        self,
        path: Path,
        events: list[dict[str, Any]],
        *,
        session_id: str,
    ) -> None:
        try:
            atomic_write_text(
                path,
                "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
            )
        except OSError as exc:
            raise EventStoreError(
                f"Failed to persist event payload for session_id={session_id} at {path}: {exc}"
            ) from exc

    def _next_seq(self, events: list[dict[str, Any]]) -> int:
        if not events:
            return 1
        return max(int(item["seq"]) for item in events) + 1

    def _events_path(self, session_id: str, *, org_id: str | None = None) -> Path:
        if not session_id or "/" in session_id or "\\" in session_id:
            raise EventStoreError(f"Invalid session_id: {session_id}")
        base = self._root_dir
        if org_id:
            base = base / org_id
        return base / f"{session_id}.jsonl"
