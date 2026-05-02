from __future__ import annotations

import pytest
from pathlib import Path

from persistence.store_factory import build_runtime_store_bundle
from seed_demo_data import run


def _snapshot(data_dir: Path, learner_id: str) -> dict | None:
    bundle = build_runtime_store_bundle(data_dir)
    return bundle.progress_store.get(learner_id)


def test_seed_demo_data_cli_seeds_selected_demo_learner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "runtime-data"

    exit_code = run(
        [
            "--data-dir",
            str(data_dir),
            "--learner-id",
            "learner_demo_001",
        ]
    )

    assert exit_code == 0
    snapshot = _snapshot(data_dir, "learner_demo_001")
    assert snapshot is not None
    assert snapshot["total_sessions"] == 100

    stdout = capsys.readouterr().out
    assert "learner_id=learner_demo_001" in stdout


def test_seed_demo_data_cli_appends_today_batch_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "runtime-data"

    exit_code = run(
        [
            "--data-dir",
            str(data_dir),
            "--append-today-sessions",
            "25",
            "--append-today-learner-id",
            "learner_demo_001",
        ]
    )

    assert exit_code == 0
    snapshot = _snapshot(data_dir, "learner_demo_001")
    assert snapshot is not None
    assert snapshot["total_sessions"] == 25

    stdout = capsys.readouterr().out
    assert "appended_today learner_id=learner_demo_001 count=25" in stdout


def test_seed_demo_data_cli_appends_today_batch_to_existing_learner(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "runtime-data"

    first_exit_code = run(
        [
            "--data-dir",
            str(data_dir),
            "--learner-id",
            "learner_demo_001",
        ]
    )
    assert first_exit_code == 0

    second_exit_code = run(
        [
            "--data-dir",
            str(data_dir),
            "--append-today-sessions",
            "25",
            "--append-today-learner-id",
            "learner_demo_001",
        ]
    )
    assert second_exit_code == 0

    snapshot = _snapshot(data_dir, "learner_demo_001")
    assert snapshot is not None
    assert snapshot["total_sessions"] == 125
