from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from persistence.file_store_support import load_json_object, load_jsonl_objects
from persistence.interfaces import EventStoreError, ProgressStoreError, SessionStoreError
from persistence.sql_codec import (
    build_progress_snapshot_row,
    build_prompt_context_snapshot_row,
    build_review_row,
    derive_skill_id_from_session_payload,
    normalize_datetime,
)
from persistence.sql_stores import (
    SQLEventStore,
    SQLProgressStore,
    SQLSessionStore,
    assert_runtime_sql_schema_ready,
    build_runtime_sql_engine,
    reset_runtime_sql_data,
)
from runtime_config import resolve_runtime_data_dir, resolve_runtime_sqlalchemy_url
from session_events import normalize_session_event_payloads


@dataclass(frozen=True)
class ImportIssue:
    artifact_type: str
    path: Path
    reason: str

    def render(self) -> str:
        return (
            "[import-file-data-to-sql] "
            f"issue artifact={self.artifact_type} path={self.path} reason={self.reason}"
        )


@dataclass(frozen=True)
class SessionImportArtifact:
    session_id: str
    path: Path
    payload: dict[str, Any]
    turn_ids: frozenset[str]


@dataclass(frozen=True)
class EventImportArtifact:
    session_id: str
    path: Path
    events: list[dict[str, Any]]


@dataclass(frozen=True)
class ProgressImportArtifact:
    learner_id: str
    path: Path
    payload: dict[str, Any]


@dataclass
class ImportSummary:
    discovered_sessions: int = 0
    valid_sessions: int = 0
    imported_sessions: int = 0
    invalid_sessions: int = 0
    discovered_event_files: int = 0
    valid_event_files: int = 0
    imported_event_files: int = 0
    imported_events: int = 0
    invalid_event_files: int = 0
    skipped_orphan_event_files: int = 0
    discovered_progress_files: int = 0
    valid_progress_files: int = 0
    imported_progress_snapshots: int = 0
    invalid_progress_files: int = 0
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def invalid_artifact_count(self) -> int:
        return self.invalid_sessions + self.invalid_event_files + self.invalid_progress_files


@dataclass(frozen=True)
class ImportScan:
    sessions: list[SessionImportArtifact]
    events: list[EventImportArtifact]
    progress_snapshots: list[ProgressImportArtifact]
    summary: ImportSummary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import file-backed runtime data into the PostgreSQL persistence schema.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Source runtime data directory. Defaults to MR_RUNTIME_DATA_DIR or apps/mr-visit-jp-runtime/.data.",
    )
    parser.add_argument(
        "--sqlalchemy-url",
        help="Target SQLAlchemy URL. Defaults to MR_RUNTIME_SQLALCHEMY_URL or the runtime alembic.ini value.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate artifacts and print the migration plan without writing to SQL. This is the default mode.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Write validated artifacts into the SQL persistence schema.",
    )
    parser.add_argument(
        "--truncate-first",
        action="store_true",
        help="Delete existing SQL runtime data before importing the file-backed data.",
    )
    return parser


def _validate_identifier(value: Any, *, label: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise ValueError(f"{label} must be a non-empty string")
    if "/" in normalized or "\\" in normalized:
        raise ValueError(f"{label} must not contain path separators")
    return normalized


def _top_level_artifact_id(root_dir: Path, path: Path) -> str:
    relative = path.relative_to(root_dir)
    if len(relative.parts) != 1:
        raise ValueError(
            "nested/org-scoped artifacts are not supported by the current SQL importer"
        )
    return path.stem


def _iter_artifact_files(root_dir: Path, pattern: str) -> list[Path]:
    if not root_dir.exists():
        return []
    return sorted(path for path in root_dir.rglob(pattern) if path.is_file())


def _resolve_session_turn_id(
    session_id: str,
    *,
    turn_index: int,
    turn: dict[str, Any],
    context: dict[str, Any],
    turn_count: int,
) -> str:
    raw_turn_id = context.get("turn_id") if turn_index == turn_count else turn.get("turn_id")
    if isinstance(raw_turn_id, str) and raw_turn_id.strip():
        return raw_turn_id.strip()
    return f"{session_id}:turn:{turn_index:04d}"


def _validate_session_payload(
    path: Path,
    *,
    expected_session_id: str,
    payload: dict[str, Any],
) -> SessionImportArtifact:
    session_id = _validate_identifier(payload.get("session_id"), label="session_id")
    if session_id != expected_session_id:
        raise ValueError(
            f"session_id mismatch: payload has {session_id!r}, file name expects {expected_session_id!r}"
        )
    _validate_identifier(payload.get("learner_id"), label="learner_id")

    prompt_context = payload.get("prompt_context")
    if prompt_context is not None and not isinstance(prompt_context, dict):
        raise ValueError("prompt_context must be an object when present")
    context = payload.get("context")
    if context is not None and not isinstance(context, dict):
        raise ValueError("context must be an object when present")
    continuity_context = payload.get("continuity_context")
    if continuity_context is not None and not isinstance(continuity_context, dict):
        raise ValueError("continuity_context must be an object when present")

    started_at = normalize_datetime(payload.get("started_at"))
    updated_at = normalize_datetime(payload.get("updated_at"), fallback=started_at)
    turn_count = int(payload.get("turn_count", 0))
    if turn_count < 0:
        raise ValueError("turn_count must be greater than or equal to zero")

    build_prompt_context_snapshot_row(
        prompt_context if isinstance(prompt_context, dict) else None,
        created_at=started_at,
        skill_id=derive_skill_id_from_session_payload(payload),
    )

    turns_payload = payload.get("turns", [])
    if turns_payload is None:
        turns_payload = []
    if not isinstance(turns_payload, list):
        raise ValueError("turns must be a list when present")

    context_payload = context if isinstance(context, dict) else {}
    seen_turn_indexes: set[int] = set()
    turn_ids: set[str] = set()
    for turn in turns_payload:
        if not isinstance(turn, dict):
            raise ValueError("turns must contain only objects")
        turn_index = int(turn.get("turn_index", 0))
        if turn_index <= 0:
            raise ValueError(f"turn_index must be greater than zero, got {turn.get('turn_index')!r}")
        if turn_index in seen_turn_indexes:
            raise ValueError(f"duplicate turn_index detected: {turn_index}")
        seen_turn_indexes.add(turn_index)
        if turn_index > turn_count:
            raise ValueError(
                f"turn_index {turn_index} exceeds turn_count {turn_count}"
            )
        director_events = turn.get("director_events")
        if director_events is not None and not isinstance(director_events, list):
            raise ValueError("director_events must be a list when present")
        normalize_datetime(turn.get("created_at"), fallback=updated_at)
        turn_ids.add(
            _resolve_session_turn_id(
                session_id,
                turn_index=turn_index,
                turn=turn,
                context=context_payload,
                turn_count=turn_count,
            )
        )

    if len(turns_payload) != turn_count:
        raise ValueError(
            f"turn_count mismatch: turn_count={turn_count} but turns length={len(turns_payload)}"
        )

    review_payload = payload.get("review")
    if review_payload is not None:
        if not isinstance(review_payload, dict):
            raise ValueError("review must be an object when present")
        build_review_row(
            session_id=session_id,
            prompt_context_id=1,
            prompt_context=prompt_context if isinstance(prompt_context, dict) else None,
            review=review_payload,
            created_at=updated_at,
        )

    return SessionImportArtifact(
        session_id=session_id,
        path=path,
        payload=payload,
        turn_ids=frozenset(turn_ids),
    )


def _validate_event_payloads(
    path: Path,
    *,
    expected_session_id: str,
    payloads: list[dict[str, Any]],
    valid_turn_ids: frozenset[str] | None = None,
) -> list[dict[str, Any]]:
    normalized_events = normalize_session_event_payloads(
        payloads,
        fallback_session_id=expected_session_id,
    )
    seen_seq: set[int] = set()
    for index, event in enumerate(normalized_events, start=1):
        session_id = _validate_identifier(event.get("session_id"), label="session_id")
        if session_id != expected_session_id:
            raise ValueError(
                f"event #{index} session_id mismatch: payload has {session_id!r}, "
                f"file name expects {expected_session_id!r}"
            )
        seq = int(event.get("seq", 0))
        if seq <= 0:
            raise ValueError(f"event #{index} has invalid seq={seq}")
        if seq in seen_seq:
            raise ValueError(f"duplicate event seq detected: {seq}")
        seen_seq.add(seq)
        turn_id = event.get("turn_id")
        if turn_id is None:
            continue
        normalized_turn_id = _validate_identifier(turn_id, label="turn_id")
        if valid_turn_ids is not None and normalized_turn_id not in valid_turn_ids:
            raise ValueError(
                f"event #{index} references unknown turn_id={normalized_turn_id!r}"
            )
    return normalized_events


def _validate_progress_payload(
    path: Path,
    *,
    expected_learner_id: str,
    payload: dict[str, Any],
) -> ProgressImportArtifact:
    learner_id = _validate_identifier(payload.get("learner_id"), label="learner_id")
    if learner_id != expected_learner_id:
        raise ValueError(
            f"learner_id mismatch: payload has {learner_id!r}, file name expects {expected_learner_id!r}"
        )

    recent_history = payload.get("recent_history")
    if recent_history is not None and not isinstance(recent_history, list):
        raise ValueError("recent_history must be a list when present")
    if isinstance(recent_history, list):
        for item in recent_history:
            if not isinstance(item, dict):
                raise ValueError("recent_history must contain only objects")
            if item.get("timestamp") is not None:
                normalize_datetime(item.get("timestamp"))

    latest_recommendations = payload.get("latest_recommendations")
    if latest_recommendations is not None and not isinstance(latest_recommendations, list):
        raise ValueError("latest_recommendations must be a list when present")

    build_progress_snapshot_row(payload)
    return ProgressImportArtifact(
        learner_id=learner_id,
        path=path,
        payload=payload,
    )


def _scan_sessions(data_dir: Path, summary: ImportSummary) -> dict[str, SessionImportArtifact]:
    sessions_dir = data_dir / "sessions"
    artifacts: dict[str, SessionImportArtifact] = {}
    for path in _iter_artifact_files(sessions_dir, "*.json"):
        summary.discovered_sessions += 1
        try:
            expected_session_id = _top_level_artifact_id(sessions_dir, path)
            payload = load_json_object(
                path,
                entity_name="session",
                identifier_name="session_id",
                identifier_value=expected_session_id,
                error_type=SessionStoreError,
            )
            artifact = _validate_session_payload(
                path,
                expected_session_id=expected_session_id,
                payload=payload,
            )
        except (SessionStoreError, ValueError, TypeError, KeyError) as exc:
            summary.invalid_sessions += 1
            summary.issues.append(ImportIssue("session", path, str(exc)))
            continue
        summary.valid_sessions += 1
        artifacts[artifact.session_id] = artifact
    return artifacts


def _scan_events(
    data_dir: Path,
    summary: ImportSummary,
    sessions: dict[str, SessionImportArtifact],
) -> list[EventImportArtifact]:
    events_dir = data_dir / "events"
    artifacts: list[EventImportArtifact] = []
    for path in _iter_artifact_files(events_dir, "*.jsonl"):
        summary.discovered_event_files += 1
        try:
            expected_session_id = _top_level_artifact_id(events_dir, path)
            payloads = load_jsonl_objects(
                path,
                entity_name="event",
                identifier_name="session_id",
                identifier_value=expected_session_id,
                error_type=EventStoreError,
            )
            session_artifact = sessions.get(expected_session_id)
            normalized_events = _validate_event_payloads(
                path,
                expected_session_id=expected_session_id,
                payloads=payloads,
                valid_turn_ids=session_artifact.turn_ids if session_artifact is not None else None,
            )
        except (EventStoreError, ValueError, TypeError, KeyError) as exc:
            summary.invalid_event_files += 1
            summary.issues.append(ImportIssue("event_file", path, str(exc)))
            continue

        if expected_session_id not in sessions:
            summary.skipped_orphan_event_files += 1
            summary.issues.append(
                ImportIssue(
                    "event_file",
                    path,
                    "no importable session payload matched this event file",
                )
            )
            continue

        summary.valid_event_files += 1
        artifacts.append(
            EventImportArtifact(
                session_id=expected_session_id,
                path=path,
                events=normalized_events,
            )
        )
    return artifacts


def _scan_progress(data_dir: Path, summary: ImportSummary) -> list[ProgressImportArtifact]:
    progress_dir = data_dir / "progress"
    artifacts: list[ProgressImportArtifact] = []
    for path in _iter_artifact_files(progress_dir, "*.json"):
        summary.discovered_progress_files += 1
        try:
            expected_learner_id = _top_level_artifact_id(progress_dir, path)
            payload = load_json_object(
                path,
                entity_name="progress",
                identifier_name="learner_id",
                identifier_value=expected_learner_id,
                error_type=ProgressStoreError,
            )
            artifact = _validate_progress_payload(
                path,
                expected_learner_id=expected_learner_id,
                payload=payload,
            )
        except (ProgressStoreError, ValueError, TypeError, KeyError) as exc:
            summary.invalid_progress_files += 1
            summary.issues.append(ImportIssue("progress", path, str(exc)))
            continue
        summary.valid_progress_files += 1
        artifacts.append(artifact)
    return artifacts


def _scan_import_artifacts(data_dir: Path) -> ImportScan:
    summary = ImportSummary()
    sessions = _scan_sessions(data_dir, summary)
    events = _scan_events(data_dir, summary, sessions)
    progress_snapshots = _scan_progress(data_dir, summary)
    return ImportScan(
        sessions=sorted(sessions.values(), key=lambda item: item.session_id),
        events=sorted(events, key=lambda item: item.session_id),
        progress_snapshots=sorted(progress_snapshots, key=lambda item: item.learner_id),
        summary=summary,
    )


def _emit_summary(
    *,
    mode: str,
    data_dir: Path,
    sqlalchemy_url: str | None,
    summary: ImportSummary,
) -> None:
    print(f"[import-file-data-to-sql] mode={mode} data_dir={data_dir}")
    print(
        "[import-file-data-to-sql] "
        f"sqlalchemy_url={sqlalchemy_url if sqlalchemy_url else '<not-resolved>'}"
    )
    print(
        "[import-file-data-to-sql] "
        f"sessions discovered={summary.discovered_sessions} "
        f"valid={summary.valid_sessions} imported={summary.imported_sessions} "
        f"invalid={summary.invalid_sessions}"
    )
    print(
        "[import-file-data-to-sql] "
        f"event_files discovered={summary.discovered_event_files} "
        f"valid={summary.valid_event_files} imported={summary.imported_event_files} "
        f"imported_events={summary.imported_events} invalid={summary.invalid_event_files} "
        f"skipped_orphan={summary.skipped_orphan_event_files}"
    )
    print(
        "[import-file-data-to-sql] "
        f"progress discovered={summary.discovered_progress_files} "
        f"valid={summary.valid_progress_files} "
        f"imported={summary.imported_progress_snapshots} "
        f"invalid={summary.invalid_progress_files}"
    )
    if summary.invalid_artifact_count:
        print(
            "[import-file-data-to-sql] "
            f"invalid_artifacts={summary.invalid_artifact_count}"
        )
    for issue in summary.issues:
        print(issue.render())


def run(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.truncate_first and not args.apply:
        parser.error("--truncate-first requires --apply")

    data_dir = (args.data_dir or resolve_runtime_data_dir()).expanduser().resolve()
    mode = "apply" if args.apply else "dry-run"
    scan = _scan_import_artifacts(data_dir)
    summary = scan.summary

    sqlalchemy_url = ""
    if args.sqlalchemy_url:
        sqlalchemy_url = str(args.sqlalchemy_url).strip()

    if summary.invalid_artifact_count:
        _emit_summary(
            mode=mode,
            data_dir=data_dir,
            sqlalchemy_url=sqlalchemy_url or None,
            summary=summary,
        )
        if args.apply:
            print("[import-file-data-to-sql] apply_aborted=true reason=invalid_artifacts")
        return 1

    if not args.apply:
        _emit_summary(
            mode=mode,
            data_dir=data_dir,
            sqlalchemy_url=sqlalchemy_url or None,
            summary=summary,
        )
        print("[import-file-data-to-sql] ready_for_apply=true")
        return 0

    if not sqlalchemy_url:
        sqlalchemy_url = str(resolve_runtime_sqlalchemy_url()).strip()
    if not sqlalchemy_url:
        raise ValueError("sqlalchemy_url must not be empty")

    engine = build_runtime_sql_engine(sqlalchemy_url)
    assert_runtime_sql_schema_ready(engine)
    if args.truncate_first:
        reset_runtime_sql_data(engine)

    sql_session_store = SQLSessionStore(engine)
    sql_event_store = SQLEventStore(engine)
    sql_progress_store = SQLProgressStore(engine)

    for artifact in scan.sessions:
        sql_session_store.upsert(artifact.session_id, artifact.payload)
        summary.imported_sessions += 1

    for artifact in scan.events:
        sql_event_store.replace(artifact.session_id, artifact.events)
        summary.imported_event_files += 1
        summary.imported_events += len(artifact.events)

    for artifact in scan.progress_snapshots:
        sql_progress_store.upsert(artifact.learner_id, artifact.payload)
        summary.imported_progress_snapshots += 1

    _emit_summary(
        mode=mode,
        data_dir=data_dir,
        sqlalchemy_url=sqlalchemy_url,
        summary=summary,
    )
    print("[import-file-data-to-sql] apply_complete=true")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
