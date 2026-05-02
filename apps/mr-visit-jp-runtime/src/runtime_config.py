from __future__ import annotations

import configparser
import os
from pathlib import Path

VALID_DEMO_SEED_MODES = {"auto", "manual", "disabled"}
VALID_PERSISTENCE_MODES = {"file", "sql"}


def resolve_runtime_data_dir() -> Path:
    env_path = os.getenv("MR_RUNTIME_DATA_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (Path(__file__).resolve().parents[1] / ".data").resolve()


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _runtime_alembic_ini_path() -> Path:
    return _runtime_root() / "alembic.ini"


def env_flag_enabled(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def resolve_runtime_persistence_mode() -> str:
    value = os.getenv("MR_RUNTIME_PERSISTENCE_MODE", "file").strip().lower()
    if value not in VALID_PERSISTENCE_MODES:
        supported_modes = ", ".join(sorted(VALID_PERSISTENCE_MODES))
        raise ValueError(
            f"Unsupported MR_RUNTIME_PERSISTENCE_MODE={value!r}. "
            f"Expected one of: {supported_modes}"
        )
    return value


def resolve_runtime_sqlalchemy_url() -> str:
    env_value = os.getenv("MR_RUNTIME_SQLALCHEMY_URL", "").strip()
    if env_value:
        return env_value

    parser = configparser.ConfigParser()
    ini_path = _runtime_alembic_ini_path()
    if not parser.read(ini_path):
        raise ValueError(f"Unable to read runtime Alembic config: {ini_path}")

    value = parser.get("alembic", "sqlalchemy.url", fallback="").strip()
    if not value:
        raise ValueError(
            "No SQLAlchemy URL configured. Set MR_RUNTIME_SQLALCHEMY_URL or "
            f"configure sqlalchemy.url in {ini_path}."
        )
    return value


def resolve_demo_seed_mode() -> str:
    value = os.getenv("MR_RUNTIME_DEMO_SEED_MODE", "").strip().lower()
    if value:
        if value not in VALID_DEMO_SEED_MODES:
            supported_modes = ", ".join(sorted(VALID_DEMO_SEED_MODES))
            raise ValueError(
                f"Unsupported MR_RUNTIME_DEMO_SEED_MODE={value!r}. "
                f"Expected one of: {supported_modes}"
            )
        return value

    # Backward compatibility for older environments while the new single-setting
    # mode is rolling out across docs and scripts.
    if env_flag_enabled("MR_RUNTIME_DISABLE_DEMO_SEED"):
        return "disabled"

    # Keep boot behavior explicit. Local convenience comes from bootstrap's
    # manual seed command unless the user opts into auto.
    return "manual"


def should_seed_demo_runtime_data_on_boot() -> bool:
    return resolve_demo_seed_mode() == "auto"
