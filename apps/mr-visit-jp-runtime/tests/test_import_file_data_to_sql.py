from __future__ import annotations

import json
from pathlib import Path

import pytest

import import_file_data_to_sql as importer


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, payloads: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in payloads),
        encoding="utf-8",
    )


def _session_payload(
    *,
    session_id: str = "sess_001",
    learner_id: str = "learner_001",
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "scenario_id": "busy_doctor_short_visit",
        "learner_id": learner_id,
        "prompt_context": {
            "profile_id": "alpha_baseline_v1",
            "experiment_id": None,
            "flags": [],
            "contracts": {},
        },
        "continuity_context": {},
        "context": {
            "skill_id": "mr_visit_jp",
            "capability_id": "practice_session",
            "persona_id": "busy_clinician_neutral",
            "prompt_profile": "alpha_baseline_v1",
            "locale": "ja-JP",
            "trace_id": f"trace_{session_id}",
        },
        "status": "finalized",
        "started_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:05:00+00:00",
        "turn_count": 1,
        "finish_reason": "manual_finish",
        "turns": [
            {
                "turn_index": 1,
                "user_message": "short update",
                "doctor_reply": "go on",
                "director_phase": "opening",
                "director_events": ["opening_missing_permission"],
                "created_at": "2026-01-01T00:01:00+00:00",
            }
        ],
        "review": {
            "overall_score": 70,
            "overall_band": "functional",
            "priority_subskills": ["opening"],
            "compliance_flags": [],
            "meta": {"artifact_sources": {"judge": "rule"}, "fallback_reasons": []},
        },
    }


def _event_payloads(
    *,
    session_id: str = "sess_001",
    learner_id: str = "learner_001",
) -> list[dict[str, object]]:
    return [
        {
            "type": "session_started",
            "source": "runtime",
            "stage": "opening",
            "content": {"hello": "world"},
            "metadata": {
                "capability_id": "practice_session",
                "action_id": "start_session",
                "learner_id": learner_id,
                "scenario_id": "busy_doctor_short_visit",
                "persona_id": "busy_clinician_neutral",
                "prompt_profile": "alpha_baseline_v1",
                "trace_id": f"trace_{session_id}",
            },
            "skill_id": "mr_visit_jp",
            "session_id": session_id,
            "turn_id": None,
            "seq": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "schema_version": "1.1",
        }
    ]


def _progress_payload(*, learner_id: str = "learner_001", session_id: str = "sess_001") -> dict[str, object]:
    return {
        "learner_id": learner_id,
        "total_sessions": 1,
        "total_exp": 42,
        "level": 1,
        "updated_at": "2026-01-01T00:05:00+00:00",
        "latest_recommendations": [
            {
                "scenario_id": "cautious_doctor_evidence_check",
                "title": "Evidence Check",
                "difficulty": "medium",
                "target_subskills": ["opening"],
                "reason": "Needs more specific evidence framing.",
            }
        ],
        "weakness_clusters": [],
        "subskills": {},
        "recent_history": [
            {
                "session_id": session_id,
                "timestamp": "2026-01-01T00:05:00+00:00",
            }
        ],
        "coach_memory": {},
        "applied_session_ids": [session_id],
    }


def test_import_file_data_to_sql_apply_imports_sessions_events_and_progress(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "runtime-data"
    _write_json(data_dir / "sessions" / "sess_001.json", _session_payload())
    _write_jsonl(data_dir / "events" / "sess_001.jsonl", _event_payloads())
    _write_json(data_dir / "progress" / "learner_001.json", _progress_payload())

    reset_calls: list[str] = []
    session_calls: list[tuple[str, dict[str, object]]] = []
    event_calls: list[tuple[str, list[dict[str, object]]]] = []
    progress_calls: list[tuple[str, dict[str, object]]] = []

    class _FakeSessionStore:
        def __init__(self, engine):
            self._engine = engine

        def upsert(self, session_id: str, payload: dict[str, object]) -> None:
            session_calls.append((session_id, payload))

    class _FakeEventStore:
        def __init__(self, engine):
            self._engine = engine

        def replace(self, session_id: str, payloads: list[dict[str, object]]) -> None:
            event_calls.append((session_id, payloads))

    class _FakeProgressStore:
        def __init__(self, engine):
            self._engine = engine

        def upsert(self, learner_id: str, payload: dict[str, object]) -> None:
            progress_calls.append((learner_id, payload))

    monkeypatch.setattr(importer, "build_runtime_sql_engine", lambda url: object())
    monkeypatch.setattr(importer, "assert_runtime_sql_schema_ready", lambda engine: None)
    monkeypatch.setattr(importer, "reset_runtime_sql_data", lambda engine: reset_calls.append("reset"))
    monkeypatch.setattr(importer, "SQLSessionStore", _FakeSessionStore)
    monkeypatch.setattr(importer, "SQLEventStore", _FakeEventStore)
    monkeypatch.setattr(importer, "SQLProgressStore", _FakeProgressStore)

    exit_code = importer.run(
        [
            "--data-dir",
            str(data_dir),
            "--sqlalchemy-url",
            "postgresql+psycopg://cosi:cosi@localhost:5432/cosi",
            "--apply",
            "--truncate-first",
        ]
    )

    assert exit_code == 0
    assert reset_calls == ["reset"]
    assert [item[0] for item in session_calls] == ["sess_001"]
    assert [item[0] for item in event_calls] == ["sess_001"]
    assert [item[0] for item in progress_calls] == ["learner_001"]

    stdout = capsys.readouterr().out
    assert "mode=apply" in stdout
    assert "sessions discovered=1 valid=1 imported=1 invalid=0" in stdout
    assert "event_files discovered=1 valid=1 imported=1 imported_events=1" in stdout
    assert "progress discovered=1 valid=1 imported=1 invalid=0" in stdout
    assert "apply_complete=true" in stdout


def test_import_file_data_to_sql_dry_run_validates_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "runtime-data"
    _write_json(data_dir / "sessions" / "sess_001.json", _session_payload())
    _write_jsonl(data_dir / "events" / "sess_001.jsonl", _event_payloads())
    _write_json(data_dir / "progress" / "learner_001.json", _progress_payload())

    build_calls: list[str] = []
    monkeypatch.setattr(importer, "build_runtime_sql_engine", lambda url: build_calls.append(url))

    exit_code = importer.run(["--data-dir", str(data_dir)])

    assert exit_code == 0
    assert build_calls == []

    stdout = capsys.readouterr().out
    assert "mode=dry-run" in stdout
    assert "sqlalchemy_url=<not-resolved>" in stdout
    assert "sessions discovered=1 valid=1 imported=0 invalid=0" in stdout
    assert "event_files discovered=1 valid=1 imported=0 imported_events=0" in stdout
    assert "progress discovered=1 valid=1 imported=0 invalid=0" in stdout
    assert "ready_for_apply=true" in stdout


def test_import_file_data_to_sql_apply_aborts_when_invalid_artifacts_are_found(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "runtime-data"
    payload = _session_payload(session_id="different_session_id")
    _write_json(data_dir / "sessions" / "sess_001.json", payload)

    build_calls: list[str] = []
    monkeypatch.setattr(importer, "build_runtime_sql_engine", lambda url: build_calls.append(url))

    exit_code = importer.run(
        [
            "--data-dir",
            str(data_dir),
            "--sqlalchemy-url",
            "postgresql+psycopg://cosi:cosi@localhost:5432/cosi",
            "--apply",
        ]
    )

    assert exit_code == 1
    assert build_calls == []

    stdout = capsys.readouterr().out
    assert "invalid_artifacts=1" in stdout
    assert "apply_aborted=true reason=invalid_artifacts" in stdout
    assert "artifact=session" in stdout
    assert "session_id mismatch" in stdout


def test_import_file_data_to_sql_reports_orphan_event_files_in_dry_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "runtime-data"
    _write_jsonl(data_dir / "events" / "sess_404.jsonl", _event_payloads(session_id="sess_404"))

    exit_code = importer.run(["--data-dir", str(data_dir), "--dry-run"])

    assert exit_code == 0

    stdout = capsys.readouterr().out
    assert "mode=dry-run" in stdout
    assert "skipped_orphan=1" in stdout
    assert "no importable session payload matched this event file" in stdout


def test_import_file_data_to_sql_rejects_truncate_first_without_apply(
    tmp_path: Path,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        importer.run(["--data-dir", str(tmp_path), "--truncate-first"])

    assert exc_info.value.code == 2
