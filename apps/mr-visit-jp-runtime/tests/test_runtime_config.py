from __future__ import annotations

import pytest

from runtime_config import (
    resolve_demo_seed_mode,
    resolve_runtime_persistence_mode,
    resolve_runtime_sqlalchemy_url,
    should_seed_demo_runtime_data_on_boot,
)


def test_resolve_demo_seed_mode_defaults_to_manual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MR_RUNTIME_DEMO_SEED_MODE", raising=False)
    monkeypatch.delenv("MR_RUNTIME_DISABLE_DEMO_SEED", raising=False)

    assert resolve_demo_seed_mode() == "manual"
    assert should_seed_demo_runtime_data_on_boot() is False


@pytest.mark.parametrize(
    ("mode", "should_seed"),
    [("auto", True), ("manual", False), ("disabled", False)],
)
def test_resolve_demo_seed_mode_supports_documented_values(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    should_seed: bool,
) -> None:
    monkeypatch.setenv("MR_RUNTIME_DEMO_SEED_MODE", mode)
    monkeypatch.delenv("MR_RUNTIME_DISABLE_DEMO_SEED", raising=False)

    assert resolve_demo_seed_mode() == mode
    assert should_seed_demo_runtime_data_on_boot() is should_seed


def test_resolve_demo_seed_mode_keeps_legacy_disable_flag_compatible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MR_RUNTIME_DEMO_SEED_MODE", raising=False)
    monkeypatch.setenv("MR_RUNTIME_DISABLE_DEMO_SEED", "1")

    assert resolve_demo_seed_mode() == "disabled"
    assert should_seed_demo_runtime_data_on_boot() is False


def test_resolve_demo_seed_mode_rejects_unknown_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MR_RUNTIME_DEMO_SEED_MODE", "surprise")

    with pytest.raises(ValueError, match="Unsupported MR_RUNTIME_DEMO_SEED_MODE"):
        resolve_demo_seed_mode()


def test_resolve_runtime_persistence_mode_defaults_to_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MR_RUNTIME_PERSISTENCE_MODE", raising=False)

    assert resolve_runtime_persistence_mode() == "file"


def test_resolve_runtime_persistence_mode_rejects_unknown_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MR_RUNTIME_PERSISTENCE_MODE", "mystery")

    with pytest.raises(ValueError, match="Unsupported MR_RUNTIME_PERSISTENCE_MODE"):
        resolve_runtime_persistence_mode()


def test_resolve_runtime_sqlalchemy_url_prefers_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MR_RUNTIME_SQLALCHEMY_URL", "postgresql+psycopg://override")

    assert resolve_runtime_sqlalchemy_url() == "postgresql+psycopg://override"


def test_resolve_runtime_sqlalchemy_url_falls_back_to_runtime_alembic_ini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MR_RUNTIME_SQLALCHEMY_URL", raising=False)

    assert resolve_runtime_sqlalchemy_url() == "postgresql+psycopg://cosi:cosi@localhost:5439/cosi"
