from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from persistence.file_event_store import FileEventStore
from persistence.file_progress_store import FileProgressStore
from persistence.file_session_store import FileSessionStore
from persistence.file_training_plan_store import FileTrainingPlanStore
from persistence.interfaces import EventStore, ProgressStore, SessionStore, TrainingPlanStore
from persistence.sql_stores import (
    SQLEventStore,
    SQLProgressStore,
    SQLSessionStore,
    SQLTrainingPlanStore,
    assert_runtime_sql_schema_ready,
    build_runtime_sql_engine,
)
from runtime_config import resolve_runtime_persistence_mode, resolve_runtime_sqlalchemy_url
from services.training_plan_service import TrainingPlanService


@dataclass(frozen=True)
class RuntimeStoreBundle:
    mode: str
    session_store: SessionStore
    event_store: EventStore
    progress_store: ProgressStore
    training_plan_service: TrainingPlanService | None = None
    sql_engine: Engine | None = None


def build_runtime_store_bundle(data_dir: Path) -> RuntimeStoreBundle:
    mode = resolve_runtime_persistence_mode()
    if mode == "file":
        plan_store: TrainingPlanStore = FileTrainingPlanStore(data_dir / "training_plans")
        return RuntimeStoreBundle(
            mode=mode,
            session_store=FileSessionStore(data_dir / "sessions"),
            event_store=FileEventStore(data_dir / "events"),
            progress_store=FileProgressStore(data_dir / "progress"),
            training_plan_service=TrainingPlanService(plan_store),
            sql_engine=None,
        )

    sqlalchemy_url = resolve_runtime_sqlalchemy_url()
    try:
        engine = build_runtime_sql_engine(sqlalchemy_url)
        assert_runtime_sql_schema_ready(engine)
    except Exception as exc:
        raise RuntimeError(
            "Failed to initialize runtime SQL persistence. "
            "Check MR_RUNTIME_SQLALCHEMY_URL, installed PostgreSQL driver, and Alembic migrations."
        ) from exc
    plan_store: TrainingPlanStore = SQLTrainingPlanStore(engine)
    return RuntimeStoreBundle(
        mode=mode,
        session_store=SQLSessionStore(engine),
        event_store=SQLEventStore(engine),
        progress_store=SQLProgressStore(engine),
        training_plan_service=TrainingPlanService(plan_store),
        sql_engine=engine,
    )
