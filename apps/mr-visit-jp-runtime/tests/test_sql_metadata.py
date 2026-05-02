from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from runtime_sql_metadata import TABLE_NAMES, runtime_persistence_metadata, sessions


EXPECTED_TABLES = {
    "learners",
    "prompt_context_snapshots",
    "sessions",
    "session_turns",
    "session_events",
    "session_reviews",
    "learner_progress_snapshots",
    "session_recommendations",
    "training_plans",
}


def test_runtime_persistence_metadata_contains_r5_base_tables() -> None:
    assert set(TABLE_NAMES) == EXPECTED_TABLES


def test_runtime_persistence_metadata_compiles_for_postgresql() -> None:
    dialect = postgresql.dialect()

    for table in runtime_persistence_metadata.sorted_tables:
        sql = str(CreateTable(table).compile(dialect=dialect))
        assert table.name in sql

        for index in table.indexes:
            index_sql = str(CreateIndex(index).compile(dialect=dialect))
            assert index.name in index_sql


def test_runtime_persistence_metadata_exposes_session_prompt_profile_columns() -> None:
    assert "prompt_profile" in sessions.c
    assert "experiment_id" in sessions.c


def test_initial_revision_file_exists() -> None:
    revision_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0001_runtime_persistence_base.py"
    )
    assert revision_path.exists()
