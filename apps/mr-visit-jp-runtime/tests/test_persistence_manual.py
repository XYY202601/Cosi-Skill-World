from pathlib import Path

from persistence.file_session_store import FileSessionStore
from persistence.file_progress_store import FileProgressStore

def test_json_persistence_completeness(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage_test"
    storage_dir.mkdir(exist_ok=True)

    session_store = FileSessionStore(storage_dir / "sessions")
    progress_store = FileProgressStore(storage_dir / "progress")

    # Test session persistence
    session_id = "test_session_1"
    session_data = {
        "session_id": session_id,
        "status": "finalized",
        "review": {"overall_score": 85},
        "continuity_context": {"carryover_focus_subskills": ["opening"]},
    }

    session_store.create(session_id, session_data)
    loaded_session = session_store.get(session_id)
    assert loaded_session["session_id"] == session_id
    assert loaded_session["review"]["overall_score"] == 85

    # Test progress persistence (with coach memory)
    learner_id = "test_learner_1"
    progress_data = {
        "learner_id": learner_id,
        "coach_memory": {
            "active_focus_subskills": ["opening"],
            "summary": "Focus on opening.",
        },
    }

    progress_store.upsert(learner_id, progress_data)
    loaded_progress = progress_store.get(learner_id)
    assert loaded_progress["learner_id"] == learner_id
    assert loaded_progress["coach_memory"]["active_focus_subskills"] == ["opening"]
