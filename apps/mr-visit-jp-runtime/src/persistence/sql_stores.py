from __future__ import annotations

from datetime import datetime
from threading import Lock
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from persistence.interfaces import (
    EventStoreError,
    ProgressStoreError,
    SessionStoreConflictError,
    SessionStoreError,
    TrainingPlanStoreError,
)
from persistence.sql_codec import (
    DEFAULT_SQL_LOCALE,
    build_event_row,
    build_progress_snapshot_row,
    build_prompt_context_snapshot_row,
    build_recommendation_rows,
    build_review_row,
    derive_last_session_at_from_progress_payload,
    derive_locale_from_session_payload,
    derive_skill_id_from_session_payload,
    derive_source_session_id_from_progress_payload,
    normalize_datetime,
    normalize_object,
    reconstruct_event_payload,
    reconstruct_prompt_context,
)
from runtime_sql_metadata import (
    learners,
    learner_progress_snapshots,
    prompt_context_snapshots,
    session_events,
    session_recommendations,
    session_reviews,
    sessions,
    session_turns,
    training_plans,
)
from session_events import normalize_session_event_payload, normalize_session_event_payloads


def build_runtime_sql_engine(sqlalchemy_url: str) -> Engine:
    return sa.create_engine(
        sqlalchemy_url,
        future=True,
        pool_pre_ping=True,
    )


def assert_runtime_sql_schema_ready(engine: Engine) -> None:
    required_tables = {
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
    inspector = sa.inspect(engine)
    discovered = set(inspector.get_table_names())
    missing = sorted(required_tables - discovered)
    if missing:
        raise RuntimeError(
            "Runtime SQL schema is missing required tables: "
            f"{', '.join(missing)}. Run Alembic upgrade head first."
        )


def reset_runtime_sql_data(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(sa.delete(session_recommendations))
        conn.execute(sa.delete(learner_progress_snapshots))
        conn.execute(sa.delete(session_reviews))
        conn.execute(sa.delete(session_events))
        conn.execute(sa.delete(session_turns))
        conn.execute(sa.delete(sessions))
        conn.execute(sa.delete(prompt_context_snapshots))
        conn.execute(sa.delete(training_plans))
        conn.execute(sa.delete(learners))


class _SQLStoreBase:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._lock = Lock()

    def _validate_id(self, value: str, *, label: str, error_type: type[RuntimeError]) -> str:
        normalized = value.strip() if isinstance(value, str) else ""
        if not normalized or "/" in normalized or "\\" in normalized:
            raise error_type(f"Invalid {label}: {value}")
        return normalized

    def _upsert_learner(
        self,
        conn: Connection,
        *,
        learner_id: str,
        locale: str,
        observed_at: datetime,
        last_session_at: datetime | None = None,
        org_id: str | None = None,
    ) -> None:
        resolved_org_id = str(org_id or "").strip() or "__unscoped__"
        existing = conn.execute(
            sa.select(learners).where(learners.c.learner_id == learner_id)
        ).mappings().first()
        if existing is None:
            conn.execute(
                learners.insert().values(
                    learner_id=learner_id,
                    org_id=resolved_org_id,
                    locale=locale or DEFAULT_SQL_LOCALE,
                    created_at=observed_at,
                    updated_at=observed_at,
                    last_session_at=last_session_at,
                )
            )
            return

        resolved_last_session_at = existing["last_session_at"]
        if last_session_at is not None:
            if resolved_last_session_at is None or last_session_at > resolved_last_session_at:
                resolved_last_session_at = last_session_at

        created_at = existing["created_at"]
        if created_at is None or observed_at < created_at:
            created_at = observed_at
        updated_at = existing["updated_at"]
        if updated_at is None or observed_at > updated_at:
            updated_at = observed_at

        conn.execute(
            learners.update()
            .where(learners.c.learner_id == learner_id)
            .values(
                org_id=resolved_org_id if not existing["org_id"] or existing["org_id"] == "__unscoped__" else existing["org_id"],
                locale=locale or existing["locale"] or DEFAULT_SQL_LOCALE,
                created_at=created_at,
                updated_at=updated_at,
                last_session_at=resolved_last_session_at,
            )
        )

    def _upsert_prompt_context_snapshot(
        self,
        conn: Connection,
        *,
        prompt_context: dict[str, Any] | None,
        created_at: datetime,
        skill_id: str,
    ) -> int:
        snapshot = build_prompt_context_snapshot_row(
            prompt_context,
            created_at=created_at,
            skill_id=skill_id,
        )
        stmt = (
            pg_insert(prompt_context_snapshots)
            .values(**snapshot)
            .on_conflict_do_update(
                index_elements=[prompt_context_snapshots.c.context_hash],
                set_={
                    "skill_id": snapshot["skill_id"],
                    "prompt_profile": snapshot["prompt_profile"],
                    "experiment_id": snapshot["experiment_id"],
                    "prompt_flags_json": snapshot["prompt_flags_json"],
                    "contracts_json": snapshot["contracts_json"],
                    "summary_json": snapshot["summary_json"],
                    "created_at": snapshot["created_at"],
                },
            )
            .returning(prompt_context_snapshots.c.prompt_context_id)
        )
        prompt_context_id = conn.execute(stmt).scalar_one()
        return int(prompt_context_id)


class SQLSessionStore(_SQLStoreBase):
    """PostgreSQL-backed session store preserving the file store payload contract."""

    def create(self, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        validated_id = self._validate_id(
            session_id,
            label="session_id",
            error_type=SessionStoreError,
        )
        with self._lock:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    sa.select(sessions.c.session_id).where(sessions.c.session_id == validated_id)
                ).scalar_one_or_none()
                if existing is not None:
                    raise SessionStoreConflictError(f"Session already exists: {validated_id}")
                self._write_session(conn, validated_id, payload, org_id=org_id)

    def upsert(self, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        validated_id = self._validate_id(
            session_id,
            label="session_id",
            error_type=SessionStoreError,
        )
        with self._lock:
            with self._engine.begin() as conn:
                self._write_session(conn, validated_id, payload, org_id=org_id)

    def get(self, session_id: str, *, org_id: str | None = None) -> dict[str, Any] | None:
        validated_id = self._validate_id(
            session_id,
            label="session_id",
            error_type=SessionStoreError,
        )
        with self._lock:
            with self._engine.connect() as conn:
                return self._load_session(conn, validated_id, org_id=org_id)

    def list_all(self, *, org_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            with self._engine.connect() as conn:
                stmt = sa.select(sessions.c.session_id).order_by(sessions.c.started_at, sessions.c.session_id)
                if org_id:
                    stmt = stmt.where(sessions.c.org_id == org_id)
                session_ids = conn.execute(stmt).scalars().all()
                payloads: list[dict[str, Any]] = []
                for session_id in session_ids:
                    payload = self._load_session(conn, str(session_id))
                    if payload is not None:
                        payloads.append(payload)
                return payloads

    def _write_session(self, conn: Connection, session_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        prompt_context = payload.get("prompt_context")
        started_at = normalize_datetime(payload.get("started_at"))
        updated_at = normalize_datetime(payload.get("updated_at"), fallback=started_at)
        locale = derive_locale_from_session_payload(payload)
        skill_id = derive_skill_id_from_session_payload(payload)
        learner_id = str(payload.get("learner_id", "")).strip()
        if not learner_id:
            raise SessionStoreError("Session payload must include learner_id")
        resolved_org_id = str(org_id or "").strip() or "__unscoped__"

        prompt_context_id = self._upsert_prompt_context_snapshot(
            conn,
            prompt_context=prompt_context if isinstance(prompt_context, dict) else None,
            created_at=started_at,
            skill_id=skill_id,
        )
        self._upsert_learner(
            conn,
            learner_id=learner_id,
            locale=locale,
            observed_at=updated_at,
            last_session_at=started_at,
            org_id=resolved_org_id,
        )

        session_row = {
            "session_id": session_id,
            "org_id": resolved_org_id,
            "learner_id": learner_id,
            "prompt_context_id": prompt_context_id,
            "skill_id": skill_id,
            "capability_id": str(normalize_object(payload.get("context")).get("capability_id", "")),
            "scenario_id": str(payload.get("scenario_id", "")),
            "persona_id": str(normalize_object(payload.get("context")).get("persona_id", "")),
            "locale": locale,
            "trace_id": str(normalize_object(payload.get("context")).get("trace_id", f"trace_{session_id}")),
            "prompt_profile": str(normalize_object(payload.get("context")).get("prompt_profile", "unknown")),
            "experiment_id": (
                str(normalize_object(payload.get("context"))["experiment_id"])
                if normalize_object(payload.get("context")).get("experiment_id") is not None
                else None
            ),
            "status": str(payload.get("status", "")),
            "turn_count": int(payload.get("turn_count", 0)),
            "finish_reason": (
                str(payload["finish_reason"]) if payload.get("finish_reason") is not None else None
            ),
            "started_at": started_at,
            "updated_at": updated_at,
            "continuity_context_json": normalize_object(payload.get("continuity_context")),
            "context_json": normalize_object(payload.get("context")),
        }
        conn.execute(
            pg_insert(sessions)
            .values(**session_row)
            .on_conflict_do_update(
                index_elements=[sessions.c.session_id],
                set_={
                    "org_id": session_row["org_id"],
                    "learner_id": session_row["learner_id"],
                    "prompt_context_id": session_row["prompt_context_id"],
                    "skill_id": session_row["skill_id"],
                    "capability_id": session_row["capability_id"],
                    "scenario_id": session_row["scenario_id"],
                    "persona_id": session_row["persona_id"],
                    "locale": session_row["locale"],
                    "trace_id": session_row["trace_id"],
                    "prompt_profile": session_row["prompt_profile"],
                    "experiment_id": session_row["experiment_id"],
                    "status": session_row["status"],
                    "turn_count": session_row["turn_count"],
                    "finish_reason": session_row["finish_reason"],
                    "started_at": session_row["started_at"],
                    "updated_at": session_row["updated_at"],
                    "continuity_context_json": session_row["continuity_context_json"],
                    "context_json": session_row["context_json"],
                },
            )
        )

        turns_payload = payload.get("turns", [])
        if isinstance(turns_payload, list):
            for turn in turns_payload:
                if not isinstance(turn, dict):
                    continue
                turn_index = int(turn.get("turn_index", 0))
                if turn_index <= 0:
                    continue
                raw_turn_id = (
                    normalize_object(payload.get("context")).get("turn_id")
                    if turn_index == int(payload.get("turn_count", 0))
                    else turn.get("turn_id")
                )
                turn_id = (
                    raw_turn_id.strip()
                    if isinstance(raw_turn_id, str) and raw_turn_id.strip()
                    else f"{session_id}:turn:{turn_index:04d}"
                )
                turn_row = {
                    "turn_id": turn_id,
                    "session_id": session_id,
                    "turn_index": turn_index,
                    "user_message": str(turn.get("user_message", "")),
                    "doctor_reply": str(turn.get("doctor_reply", "")),
                    "director_phase": str(turn.get("director_phase", "")),
                    "director_events_json": list(turn.get("director_events", []))
                    if isinstance(turn.get("director_events"), list)
                    else [],
                    "created_at": normalize_datetime(turn.get("created_at"), fallback=updated_at),
                }
                conn.execute(
                    pg_insert(session_turns)
                    .values(**turn_row)
                    .on_conflict_do_update(
                        index_elements=[session_turns.c.turn_id],
                        set_={
                            "session_id": turn_row["session_id"],
                            "turn_index": turn_row["turn_index"],
                            "user_message": turn_row["user_message"],
                            "doctor_reply": turn_row["doctor_reply"],
                            "director_phase": turn_row["director_phase"],
                            "director_events_json": turn_row["director_events_json"],
                            "created_at": turn_row["created_at"],
                        },
                    )
                )

            conn.execute(
                session_turns.delete().where(
                    sa.and_(
                        session_turns.c.session_id == session_id,
                        session_turns.c.turn_index > int(payload.get("turn_count", 0)),
                    )
                )
            )

        review_payload = payload.get("review")
        if isinstance(review_payload, dict):
            review_row = build_review_row(
                session_id=session_id,
                prompt_context_id=prompt_context_id,
                prompt_context=prompt_context if isinstance(prompt_context, dict) else None,
                review=review_payload,
                created_at=updated_at,
            )
            conn.execute(
                pg_insert(session_reviews)
                .values(**review_row)
                .on_conflict_do_update(
                    index_elements=[session_reviews.c.session_id],
                    set_={
                        "prompt_context_id": review_row["prompt_context_id"],
                        "overall_score": review_row["overall_score"],
                        "overall_band": review_row["overall_band"],
                        "priority_subskills": review_row["priority_subskills"],
                        "compliance_rule_ids": review_row["compliance_rule_ids"],
                        "compliance_severities": review_row["compliance_severities"],
                        "artifact_sources_json": review_row["artifact_sources_json"],
                        "fallback_reasons_json": review_row["fallback_reasons_json"],
                        "prompt_profile": review_row["prompt_profile"],
                        "experiment_id": review_row["experiment_id"],
                        "created_at": review_row["created_at"],
                        "payload_json": review_row["payload_json"],
                    },
                )
            )
        else:
            conn.execute(
                session_reviews.delete().where(session_reviews.c.session_id == session_id)
            )

    def _load_session(self, conn: Connection, session_id: str, *, org_id: str | None = None) -> dict[str, Any] | None:
        stmt = sa.select(sessions).where(sessions.c.session_id == session_id)
        if org_id:
            stmt = stmt.where(sessions.c.org_id == org_id)
        session_row = conn.execute(stmt).mappings().first()
        if session_row is None:
            return None

        prompt_row = conn.execute(
            sa.select(prompt_context_snapshots).where(
                prompt_context_snapshots.c.prompt_context_id == session_row["prompt_context_id"]
            )
        ).mappings().first()
        if prompt_row is None:
            raise SessionStoreError(f"Missing prompt context snapshot for session: {session_id}")

        turns_rows = conn.execute(
            sa.select(session_turns)
            .where(session_turns.c.session_id == session_id)
            .order_by(session_turns.c.turn_index)
        ).mappings().all()
        review_row = conn.execute(
            sa.select(session_reviews).where(session_reviews.c.session_id == session_id)
        ).mappings().first()

        return {
            "session_id": str(session_row["session_id"]),
            "scenario_id": str(session_row["scenario_id"]),
            "learner_id": str(session_row["learner_id"]),
            "prompt_context": reconstruct_prompt_context(
                prompt_profile=str(prompt_row["prompt_profile"]),
                experiment_id=prompt_row["experiment_id"],
                prompt_flags_json=prompt_row["prompt_flags_json"],
                contracts_json=prompt_row["contracts_json"],
                summary_json=prompt_row["summary_json"],
            ),
            "continuity_context": normalize_object(session_row["continuity_context_json"]),
            "context": normalize_object(session_row["context_json"]),
            "status": str(session_row["status"]),
            "started_at": normalize_datetime(session_row["started_at"]).isoformat(),
            "updated_at": normalize_datetime(session_row["updated_at"]).isoformat(),
            "turn_count": int(session_row["turn_count"]),
            "finish_reason": session_row["finish_reason"],
            "turns": [
                {
                    "turn_index": int(turn["turn_index"]),
                    "user_message": str(turn["user_message"]),
                    "doctor_reply": str(turn["doctor_reply"]),
                    "director_phase": str(turn["director_phase"]),
                    "director_events": list(turn["director_events_json"] or []),
                    "created_at": normalize_datetime(turn["created_at"]).isoformat(),
                }
                for turn in turns_rows
            ],
            "review": normalize_object(review_row["payload_json"]) if review_row is not None else None,
        }


class SQLEventStore(_SQLStoreBase):
    """PostgreSQL-backed event store preserving the event envelope contract."""

    def append(self, session_id: str, event: dict[str, Any], *, org_id: str | None = None) -> None:
        validated_id = self._validate_id(
            session_id,
            label="session_id",
            error_type=EventStoreError,
        )
        with self._lock:
            with self._engine.begin() as conn:
                next_seq = conn.execute(
                    sa.select(sa.func.max(session_events.c.seq)).where(
                        session_events.c.session_id == validated_id
                    )
                ).scalar_one()
                normalized = normalize_session_event_payload(
                    event,
                    fallback_session_id=validated_id,
                    inferred_seq=(int(next_seq) + 1) if next_seq is not None else 1,
                )
                conn.execute(session_events.insert().values(**build_event_row(normalized, org_id=org_id)))

    def replace(self, session_id: str, events: list[dict[str, Any]], *, org_id: str | None = None) -> None:
        validated_id = self._validate_id(
            session_id,
            label="session_id",
            error_type=EventStoreError,
        )
        with self._lock:
            with self._engine.begin() as conn:
                normalized_events = normalize_session_event_payloads(
                    events,
                    fallback_session_id=validated_id,
                )
                conn.execute(
                    session_events.delete().where(session_events.c.session_id == validated_id)
                )
                if normalized_events:
                    conn.execute(
                        session_events.insert(),
                        [build_event_row(event, org_id=org_id) for event in normalized_events],
                    )

    def list_events(self, session_id: str, *, org_id: str | None = None) -> list[dict[str, Any]]:
        validated_id = self._validate_id(
            session_id,
            label="session_id",
            error_type=EventStoreError,
        )
        with self._lock:
            with self._engine.connect() as conn:
                if org_id:
                    session_check = conn.execute(
                        sa.select(sessions.c.session_id).where(
                            sa.and_(
                                sessions.c.session_id == validated_id,
                                sessions.c.org_id == org_id,
                            )
                        )
                    ).scalar_one_or_none()
                    if session_check is None:
                        return []
                rows = conn.execute(
                    sa.select(session_events)
                    .where(session_events.c.session_id == validated_id)
                    .order_by(session_events.c.seq)
                ).mappings().all()
                return [
                    reconstruct_event_payload(dict(row))
                    for row in rows
                ]


class SQLProgressStore(_SQLStoreBase):
    """PostgreSQL-backed learner progress store preserving the snapshot payload contract."""

    def upsert(self, learner_id: str, payload: dict[str, Any], *, org_id: str | None = None) -> None:
        validated_id = self._validate_id(
            learner_id,
            label="learner_id",
            error_type=ProgressStoreError,
        )
        with self._lock:
            with self._engine.begin() as conn:
                snapshot_row = build_progress_snapshot_row(payload, org_id=org_id)
                if snapshot_row["learner_id"] != validated_id:
                    raise ProgressStoreError(
                        f"Progress payload learner_id mismatch: {snapshot_row['learner_id']} != {validated_id}"
                    )

                updated_at = snapshot_row["updated_at"]
                last_session_at = derive_last_session_at_from_progress_payload(payload)
                self._upsert_learner(
                    conn,
                    learner_id=validated_id,
                    locale=DEFAULT_SQL_LOCALE,
                    observed_at=updated_at,
                    last_session_at=last_session_at,
                    org_id=org_id,
                )

                existing_snapshot_id = conn.execute(
                    sa.select(learner_progress_snapshots.c.progress_snapshot_id).where(
                        sa.and_(
                            learner_progress_snapshots.c.learner_id == validated_id,
                            learner_progress_snapshots.c.updated_at == updated_at,
                            learner_progress_snapshots.c.source_session_id
                            == snapshot_row["source_session_id"],
                        )
                    )
                ).scalar_one_or_none()

                if existing_snapshot_id is None:
                    progress_snapshot_id = conn.execute(
                        learner_progress_snapshots.insert()
                        .values(**snapshot_row)
                        .returning(learner_progress_snapshots.c.progress_snapshot_id)
                    ).scalar_one()
                else:
                    progress_snapshot_id = existing_snapshot_id
                    conn.execute(
                        learner_progress_snapshots.update()
                        .where(
                            learner_progress_snapshots.c.progress_snapshot_id == progress_snapshot_id
                        )
                        .values(**snapshot_row)
                    )

                conn.execute(
                    session_recommendations.delete().where(
                        session_recommendations.c.progress_snapshot_id == progress_snapshot_id
                    )
                )
                recommendation_rows = build_recommendation_rows(
                    progress_snapshot_id=int(progress_snapshot_id),
                    learner_id=validated_id,
                    source_session_id=derive_source_session_id_from_progress_payload(payload),
                    updated_at=updated_at,
                    recommendations=payload.get("latest_recommendations"),
                )
                if recommendation_rows:
                    conn.execute(session_recommendations.insert(), recommendation_rows)

    def get(self, learner_id: str, *, org_id: str | None = None) -> dict[str, Any] | None:
        validated_id = self._validate_id(
            learner_id,
            label="learner_id",
            error_type=ProgressStoreError,
        )
        with self._lock:
            with self._engine.connect() as conn:
                stmt = (
                    sa.select(learner_progress_snapshots.c.payload_json)
                    .where(learner_progress_snapshots.c.learner_id == validated_id)
                )
                if org_id:
                    stmt = stmt.where(learner_progress_snapshots.c.org_id == org_id)
                row = conn.execute(
                    stmt.order_by(
                        learner_progress_snapshots.c.updated_at.desc(),
                        learner_progress_snapshots.c.progress_snapshot_id.desc(),
                    )
                    .limit(1)
                ).scalar_one_or_none()
                if row is None:
                    return None
                return normalize_object(row)


class SQLTrainingPlanStore(_SQLStoreBase):
    """PostgreSQL-backed training plan store."""

    def create(self, plan: dict[str, Any]) -> None:
        plan_id = str(plan.get("plan_id", ""))
        if not plan_id:
            raise TrainingPlanStoreError("plan_id is required")
        validated_id = self._validate_id(
            plan_id, label="plan_id", error_type=TrainingPlanStoreError,
        )
        with self._lock:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    sa.select(training_plans.c.plan_id).where(
                        training_plans.c.plan_id == validated_id
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    raise TrainingPlanStoreError(
                        f"Training plan already exists: {validated_id}"
                    )
                conn.execute(training_plans.insert().values(**self._plan_row(plan)))

    def update(self, plan_id: str, payload: dict[str, Any]) -> None:
        validated_id = self._validate_id(
            plan_id, label="plan_id", error_type=TrainingPlanStoreError,
        )
        with self._lock:
            with self._engine.begin() as conn:
                conn.execute(
                    training_plans.update()
                    .where(training_plans.c.plan_id == validated_id)
                    .values(**self._plan_row(payload))
                )

    def get(self, plan_id: str) -> dict[str, Any] | None:
        validated_id = self._validate_id(
            plan_id, label="plan_id", error_type=TrainingPlanStoreError,
        )
        with self._lock:
            with self._engine.connect() as conn:
                row = conn.execute(
                    sa.select(training_plans.c.payload_json).where(
                        training_plans.c.plan_id == validated_id
                    )
                ).scalar_one_or_none()
                if row is None:
                    return None
                return normalize_object(row)

    def list_all(
        self,
        *,
        org_id: str | None = None,
        learner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            with self._engine.connect() as conn:
                stmt = sa.select(training_plans.c.payload_json).order_by(
                    training_plans.c.updated_at.desc()
                )
                if org_id:
                    stmt = stmt.where(training_plans.c.org_id == org_id)
                if learner_id:
                    stmt = stmt.where(
                        training_plans.c.assigned_learners.any(learner_id)
                    )
                rows = conn.execute(stmt).scalars().all()
                return [normalize_object(row) for row in rows]

    def delete(self, plan_id: str) -> None:
        validated_id = self._validate_id(
            plan_id, label="plan_id", error_type=TrainingPlanStoreError,
        )
        with self._lock:
            with self._engine.begin() as conn:
                conn.execute(
                    training_plans.delete().where(
                        training_plans.c.plan_id == validated_id
                    )
                )

    @staticmethod
    def _plan_row(plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "plan_id": str(plan.get("plan_id", "")),
            "org_id": str(plan.get("org_id", "")),
            "title": str(plan.get("title", "")),
            "description": str(plan.get("description", "")),
            "owner_id": str(plan.get("owner_id", "")),
            "assigned_learners": list(plan.get("assigned_learners", [])),
            "assigned_cohorts": list(plan.get("assigned_cohorts", [])),
            "target_subskills": list(plan.get("target_subskills", [])),
            "required_scenario_ids": list(plan.get("required_scenario_ids", [])),
            "due_date": plan.get("due_date"),
            "goal_criteria": str(plan.get("goal_criteria", "")),
            "success_threshold": float(plan.get("success_threshold", 4.0)),
            "review_cadence": str(plan.get("review_cadence", "after_each_session")),
            "status": str(plan.get("status", "active")),
            "created_at": normalize_datetime(plan.get("created_at")),
            "updated_at": normalize_datetime(plan.get("updated_at")),
            "version": int(plan.get("version", 1)),
            "payload_json": normalize_object(plan),
        }
