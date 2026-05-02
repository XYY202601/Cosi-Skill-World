from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import seed_training_data as module


class _FakeSessionStore:
    def __init__(self) -> None:
        self.payload_by_session_id: dict[str, dict[str, object]] = {}

    def get(self, session_id: str) -> dict[str, object] | None:
        return self.payload_by_session_id.get(session_id)


class _FakeProgressStore:
    def __init__(self) -> None:
        self.total_sessions_by_learner: dict[str, int] = {}

    def get(self, learner_id: str) -> dict[str, object]:
        return {
            "learner_id": learner_id,
            "total_sessions": self.total_sessions_by_learner.get(learner_id, 0),
        }


def test_seed_training_data_requires_sql_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bundle = SimpleNamespace(
        mode="file",
        session_store=None,
        event_store=None,
        progress_store=None,
        sql_engine=None,
    )
    monkeypatch.setattr(module, "build_runtime_store_bundle", lambda _: fake_bundle)

    with pytest.raises(RuntimeError, match="MR_RUNTIME_PERSISTENCE_MODE=sql"):
        module.run(["--data-dir", str(tmp_path)])


def test_seed_training_data_generates_three_learners_with_turn_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_store = _FakeSessionStore()
    progress_store = _FakeProgressStore()
    fake_store_bundle = SimpleNamespace(
        mode="sql",
        session_store=session_store,
        event_store=object(),
        progress_store=progress_store,
        sql_engine=object(),
    )

    monkeypatch.setattr(module, "build_runtime_store_bundle", lambda _: fake_store_bundle)
    monkeypatch.setattr(module, "reset_runtime_sql_data", lambda _: None)
    monkeypatch.setattr(
        module,
        "get_domain_bundle",
        lambda: SimpleNamespace(
            scenarios={"scenario_a": object(), "scenario_b": object()},
            manifest={"subskills": ["opening", "need_discovery"]},
            curriculum={},
        ),
    )
    monkeypatch.setattr(
        module,
        "EvaluationGateService",
        lambda **_: SimpleNamespace(effective_prompt_context={"profile_id": "alpha_baseline_v1", "contracts": {}}),
    )
    monkeypatch.setattr(module, "ProgressTracker", lambda **_: object())
    monkeypatch.setattr(module, "load_runtime_prompt_context_from_env", lambda: {"profile_id": "alpha_baseline_v1"})
    monkeypatch.setattr(module, "env_flag_enabled", lambda _name: False)
    monkeypatch.setattr(module, "_read_running_runtime_mode", lambda: "sql")

    called_learners: list[str] = []

    def _fake_append(**kwargs):
        learner_id = str(kwargs["learner_id"])
        session_count = int(kwargs["session_count"])
        min_turns = int(kwargs["min_turns"])
        max_turns = int(kwargs["max_turns"])
        called_learners.append(learner_id)
        created_ids: list[str] = []
        window = max_turns - min_turns + 1
        for index in range(session_count):
            session_id = f"{learner_id}_session_{index + 1:03d}"
            turn_count = min_turns + (index % window)
            session_store.payload_by_session_id[session_id] = {
                "session_id": session_id,
                "turn_count": turn_count,
            }
            created_ids.append(session_id)
        progress_store.total_sessions_by_learner[learner_id] = session_count
        return created_ids

    monkeypatch.setattr(module, "append_comprehensive_today_sessions", _fake_append)

    exit_code = module.run(
        [
            "--data-dir",
            str(tmp_path),
            "--sessions-per-learner",
            "8",
            "--min-turns",
            "5",
            "--max-turns",
            "10",
            "--truncate-sql-first",
        ]
    )

    assert exit_code == 0
    assert called_learners == ["learner_A", "learner_B", "learner_C"]
    stdout = capsys.readouterr().out
    assert "learner_id=learner_A created_sessions=8 turn_count_min=5 turn_count_max=10" in stdout
    assert "learner_id=learner_B created_sessions=8 turn_count_min=5 turn_count_max=10" in stdout
    assert "learner_id=learner_C created_sessions=8 turn_count_min=5 turn_count_max=10" in stdout
    assert "mode=sql scenario_count=2 prompt_profile=alpha_baseline_v1" in stdout


def test_seed_training_data_aborts_when_running_runtime_mode_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store_bundle = SimpleNamespace(
        mode="sql",
        session_store=object(),
        event_store=object(),
        progress_store=object(),
        sql_engine=object(),
    )
    monkeypatch.setattr(module, "build_runtime_store_bundle", lambda _: fake_store_bundle)
    monkeypatch.setattr(module, "_read_running_runtime_mode", lambda: "file")

    with pytest.raises(RuntimeError, match="Running runtime persistence_mode does not match"):
        module.run(["--data-dir", str(tmp_path)])
