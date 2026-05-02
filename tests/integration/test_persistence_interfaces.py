from persistence.file_event_store import FileEventStore
from persistence.file_progress_store import FileProgressStore
from persistence.file_session_store import FileSessionStore
from persistence.interfaces import EventStore, ProgressStore, SessionStore


def test_file_stores_match_runtime_protocols(tmp_path):
    session_store = FileSessionStore(tmp_path / "sessions")
    event_store = FileEventStore(tmp_path / "events")
    progress_store = FileProgressStore(tmp_path / "progress")

    assert isinstance(session_store, SessionStore)
    assert isinstance(event_store, EventStore)
    assert isinstance(progress_store, ProgressStore)
