from __future__ import annotations

import os

import pytest
from sqlalchemy.engine import Engine

from persistence.sql_stores import (
    assert_runtime_sql_schema_ready,
    build_runtime_sql_engine,
    reset_runtime_sql_data,
)


@pytest.fixture(scope="session")
def sql_engine() -> Engine | None:  # type: ignore[misc]
    mode = os.environ.get("MR_RUNTIME_PERSISTENCE_MODE", "file")
    if mode != "sql":
        yield None
        return
    url = os.environ.get(
        "MR_RUNTIME_SQLALCHEMY_URL",
        "postgresql+psycopg://cosi:cosi@localhost:5439/cosi",
    )
    engine = build_runtime_sql_engine(url)
    assert_runtime_sql_schema_ready(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def isolate_sql_data(sql_engine: Engine | None) -> None:
    if sql_engine is not None:
        reset_runtime_sql_data(sql_engine)


@pytest.fixture(autouse=True)
def set_sql_persistence_mode(
    monkeypatch: pytest.MonkeyPatch,
    sql_engine: Engine | None,
) -> None:
    if sql_engine is not None:
        monkeypatch.setenv("MR_RUNTIME_PERSISTENCE_MODE", "sql")
