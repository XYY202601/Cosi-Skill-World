from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from persistence.file_event_store import FileEventStore
from persistence.file_progress_store import FileProgressStore
from persistence.file_session_store import FileSessionStore
from persistence.interfaces import EventStoreError, ProgressStoreError, SessionStoreError


def test_file_session_store_list_all_skips_corrupted_payloads(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="mr_visit_jp_runtime.persistence")
    store = FileSessionStore(tmp_path / "sessions")
    store.create(
        "sess_valid",
        {
            "session_id": "sess_valid",
            "status": "running",
        },
    )
    broken_path = tmp_path / "sessions" / "sess_broken.json"
    broken_path.write_text('{"session_id": "sess_broken",', encoding="utf-8")

    payloads = store.list_all()

    assert [item["session_id"] for item in payloads] == ["sess_valid"]
    warning_messages = [record.message for record in caplog.records]
    assert any("sess_broken" in message for message in warning_messages)
    assert any(str(broken_path) in message for message in warning_messages)


def test_file_session_store_corruption_error_includes_session_context(tmp_path: Path) -> None:
    store = FileSessionStore(tmp_path / "sessions")
    broken_path = tmp_path / "sessions" / "sess_bad.json"
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_text("{", encoding="utf-8")

    with pytest.raises(SessionStoreError) as exc_info:
        store.get("sess_bad")

    message = str(exc_info.value)
    assert "session_id=sess_bad" in message
    assert str(broken_path) in message
    assert "line 1" in message


def test_file_event_store_corruption_error_includes_session_path_and_line(
    tmp_path: Path,
) -> None:
    store = FileEventStore(tmp_path / "events")
    broken_path = tmp_path / "events" / "sess_events_bad.jsonl"
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    valid_event = {
        "type": "session_started",
        "source": "runtime",
        "stage": "practice_session",
        "content": {"status": "started"},
        "metadata": {
            "skill_id": "mr_visit_jp",
            "session_id": "sess_events_bad",
            "trace_id": "trace_sess_events_bad",
        },
        "skill_id": "mr_visit_jp",
        "session_id": "sess_events_bad",
        "turn_id": None,
        "seq": 1,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "schema_version": "1.1",
    }
    broken_path.write_text(
        json.dumps(valid_event, ensure_ascii=False) + '\n{"type":',
        encoding="utf-8",
    )

    with pytest.raises(EventStoreError) as exc_info:
        store.list_events("sess_events_bad")

    message = str(exc_info.value)
    assert "session_id=sess_events_bad" in message
    assert str(broken_path) in message
    assert "line 2" in message


def test_file_progress_store_corruption_error_includes_learner_context(
    tmp_path: Path,
) -> None:
    store = FileProgressStore(tmp_path / "progress")
    broken_path = tmp_path / "progress" / "learner_bad.json"
    broken_path.parent.mkdir(parents=True, exist_ok=True)
    broken_path.write_text("{", encoding="utf-8")

    with pytest.raises(ProgressStoreError) as exc_info:
        store.get("learner_bad")

    message = str(exc_info.value)
    assert "learner_id=learner_bad" in message
    assert str(broken_path) in message
    assert "line 1" in message
