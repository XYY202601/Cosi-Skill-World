from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

runtime_persistence_metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _text_array() -> postgresql.ARRAY:
    return postgresql.ARRAY(sa.Text())


learners = sa.Table(
    "learners",
    runtime_persistence_metadata,
    sa.Column("learner_id", sa.Text(), primary_key=True),
    sa.Column("org_id", sa.Text(), nullable=False),
    sa.Column("locale", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_session_at", sa.DateTime(timezone=True), nullable=True),
)

sa.Index("ix_learners_org_id_learner_id", learners.c.org_id, learners.c.learner_id)


prompt_context_snapshots = sa.Table(
    "prompt_context_snapshots",
    runtime_persistence_metadata,
    sa.Column("prompt_context_id", sa.BigInteger(), primary_key=True, autoincrement=True),
    sa.Column("context_hash", sa.Text(), nullable=False),
    sa.Column("skill_id", sa.Text(), nullable=False),
    sa.Column("prompt_profile", sa.Text(), nullable=False),
    sa.Column("experiment_id", sa.Text(), nullable=True),
    sa.Column("prompt_flags_json", _jsonb(), nullable=False),
    sa.Column("contracts_json", _jsonb(), nullable=False),
    sa.Column("summary_json", _jsonb(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("context_hash"),
)


sessions = sa.Table(
    "sessions",
    runtime_persistence_metadata,
    sa.Column("session_id", sa.Text(), primary_key=True),
    sa.Column("learner_id", sa.Text(), sa.ForeignKey("learners.learner_id", ondelete="CASCADE"), nullable=False),
    sa.Column("org_id", sa.Text(), nullable=False),
    sa.Column(
        "prompt_context_id",
        sa.BigInteger(),
        sa.ForeignKey("prompt_context_snapshots.prompt_context_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("skill_id", sa.Text(), nullable=False),
    sa.Column("capability_id", sa.Text(), nullable=False),
    sa.Column("scenario_id", sa.Text(), nullable=False),
    sa.Column("persona_id", sa.Text(), nullable=False),
    sa.Column("locale", sa.Text(), nullable=False),
    sa.Column("trace_id", sa.Text(), nullable=False),
    sa.Column("prompt_profile", sa.Text(), nullable=False),
    sa.Column("experiment_id", sa.Text(), nullable=True),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("turn_count", sa.Integer(), nullable=False),
    sa.Column("finish_reason", sa.Text(), nullable=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("continuity_context_json", _jsonb(), nullable=False),
    sa.Column("context_json", _jsonb(), nullable=False),
)

sa.Index("ix_sessions_learner_id_started_at", sessions.c.learner_id, sessions.c.started_at.desc())
sa.Index("ix_sessions_status_updated_at", sessions.c.status, sessions.c.updated_at.desc())
sa.Index("ix_sessions_scenario_id_started_at", sessions.c.scenario_id, sessions.c.started_at.desc())
sa.Index("ix_sessions_persona_id_started_at", sessions.c.persona_id, sessions.c.started_at.desc())
sa.Index(
    "ix_sessions_prompt_profile_experiment_id_started_at",
    sessions.c.prompt_profile,
    sessions.c.experiment_id,
    sessions.c.started_at.desc(),
)
sa.Index("ix_sessions_trace_id", sessions.c.trace_id)

sa.Index("ix_sessions_org_id_started_at", sessions.c.org_id, sessions.c.started_at.desc())


session_turns = sa.Table(
    "session_turns",
    runtime_persistence_metadata,
    sa.Column("turn_id", sa.Text(), primary_key=True),
    sa.Column("session_id", sa.Text(), sa.ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False),
    sa.Column("turn_index", sa.Integer(), nullable=False),
    sa.Column("user_message", sa.Text(), nullable=False),
    sa.Column("doctor_reply", sa.Text(), nullable=False),
    sa.Column("director_phase", sa.Text(), nullable=False),
    sa.Column("director_events_json", _jsonb(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("session_id", "turn_index"),
)


session_events = sa.Table(
    "session_events",
    runtime_persistence_metadata,
    sa.Column("event_id", sa.BigInteger(), primary_key=True, autoincrement=True),
    sa.Column("session_id", sa.Text(), sa.ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False),
    sa.Column("org_id", sa.Text(), nullable=False),
    sa.Column("turn_id", sa.Text(), sa.ForeignKey("session_turns.turn_id", ondelete="SET NULL"), nullable=True),
    sa.Column("seq", sa.Integer(), nullable=False),
    sa.Column("type", sa.Text(), nullable=False),
    sa.Column("source", sa.Text(), nullable=False),
    sa.Column("stage", sa.Text(), nullable=False),
    sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
    sa.Column("schema_version", sa.Text(), nullable=False),
    sa.Column("skill_id", sa.Text(), nullable=False),
    sa.Column("capability_id", sa.Text(), nullable=False),
    sa.Column("action_id", sa.Text(), nullable=False),
    sa.Column("learner_id", sa.Text(), nullable=False),
    sa.Column("scenario_id", sa.Text(), nullable=False),
    sa.Column("persona_id", sa.Text(), nullable=False),
    sa.Column("prompt_profile", sa.Text(), nullable=False),
    sa.Column("experiment_id", sa.Text(), nullable=True),
    sa.Column("trace_id", sa.Text(), nullable=False),
    sa.Column("content_json", _jsonb(), nullable=False),
    sa.Column("metadata_json", _jsonb(), nullable=False),
    sa.UniqueConstraint("session_id", "seq"),
)

sa.Index("ix_session_events_session_id_timestamp", session_events.c.session_id, session_events.c.timestamp)
sa.Index("ix_session_events_type_stage_timestamp", session_events.c.type, session_events.c.stage, session_events.c.timestamp.desc())
sa.Index("ix_session_events_trace_id_timestamp", session_events.c.trace_id, session_events.c.timestamp)
sa.Index(
    "ix_session_events_prompt_profile_experiment_id_timestamp",
    session_events.c.prompt_profile,
    session_events.c.experiment_id,
    session_events.c.timestamp.desc(),
)
sa.Index("ix_session_events_org_id_timestamp", session_events.c.org_id, session_events.c.timestamp)


session_reviews = sa.Table(
    "session_reviews",
    runtime_persistence_metadata,
    sa.Column("session_id", sa.Text(), sa.ForeignKey("sessions.session_id", ondelete="CASCADE"), primary_key=True),
    sa.Column(
        "prompt_context_id",
        sa.BigInteger(),
        sa.ForeignKey("prompt_context_snapshots.prompt_context_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("overall_score", sa.Integer(), nullable=False),
    sa.Column("overall_band", sa.Text(), nullable=False),
    sa.Column("priority_subskills", _text_array(), nullable=False),
    sa.Column("compliance_rule_ids", _text_array(), nullable=False),
    sa.Column("compliance_severities", _text_array(), nullable=False),
    sa.Column("artifact_sources_json", _jsonb(), nullable=False),
    sa.Column("fallback_reasons_json", _jsonb(), nullable=False),
    sa.Column("prompt_profile", sa.Text(), nullable=False),
    sa.Column("experiment_id", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("payload_json", _jsonb(), nullable=False),
)

sa.Index("ix_session_reviews_overall_band_created_at", session_reviews.c.overall_band, session_reviews.c.created_at.desc())
sa.Index(
    "ix_session_reviews_prompt_profile_experiment_id_created_at",
    session_reviews.c.prompt_profile,
    session_reviews.c.experiment_id,
    session_reviews.c.created_at.desc(),
)
sa.Index(
    "ix_session_reviews_priority_subskills_gin",
    session_reviews.c.priority_subskills,
    postgresql_using="gin",
)
sa.Index(
    "ix_session_reviews_compliance_rule_ids_gin",
    session_reviews.c.compliance_rule_ids,
    postgresql_using="gin",
)
sa.Index(
    "ix_session_reviews_compliance_severities_gin",
    session_reviews.c.compliance_severities,
    postgresql_using="gin",
)


learner_progress_snapshots = sa.Table(
    "learner_progress_snapshots",
    runtime_persistence_metadata,
    sa.Column("progress_snapshot_id", sa.BigInteger(), primary_key=True, autoincrement=True),
    sa.Column("learner_id", sa.Text(), sa.ForeignKey("learners.learner_id", ondelete="CASCADE"), nullable=False),
    sa.Column("org_id", sa.Text(), nullable=False),
    sa.Column("source_session_id", sa.Text(), sa.ForeignKey("sessions.session_id", ondelete="SET NULL"), nullable=True),
    sa.Column("total_sessions", sa.Integer(), nullable=False),
    sa.Column("total_exp", sa.Integer(), nullable=False),
    sa.Column("level", sa.Integer(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("subskills_json", _jsonb(), nullable=False),
    sa.Column("weakness_clusters_json", _jsonb(), nullable=False),
    sa.Column("recent_history_json", _jsonb(), nullable=False),
    sa.Column("coach_memory_json", _jsonb(), nullable=False),
    sa.Column("payload_json", _jsonb(), nullable=False),
)

sa.Index(
    "ix_learner_progress_snapshots_learner_id_updated_at",
    learner_progress_snapshots.c.learner_id,
    learner_progress_snapshots.c.updated_at.desc(),
)
sa.Index(
    "ix_learner_progress_snapshots_org_id_updated_at",
    learner_progress_snapshots.c.org_id,
    learner_progress_snapshots.c.updated_at.desc(),
)


session_recommendations = sa.Table(
    "session_recommendations",
    runtime_persistence_metadata,
    sa.Column("recommendation_id", sa.BigInteger(), primary_key=True, autoincrement=True),
    sa.Column(
        "progress_snapshot_id",
        sa.BigInteger(),
        sa.ForeignKey(
            "learner_progress_snapshots.progress_snapshot_id",
            ondelete="CASCADE",
            name="fk_session_recommendations_progress_snapshot",
        ),
        nullable=False,
    ),
    sa.Column("learner_id", sa.Text(), sa.ForeignKey("learners.learner_id", ondelete="CASCADE"), nullable=False),
    sa.Column("source_session_id", sa.Text(), sa.ForeignKey("sessions.session_id", ondelete="SET NULL"), nullable=True),
    sa.Column("rank", sa.Integer(), nullable=False),
    sa.Column("scenario_id", sa.Text(), nullable=False),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("difficulty", sa.Text(), nullable=False),
    sa.Column("target_subskills", _text_array(), nullable=False),
    sa.Column("reason", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("progress_snapshot_id", "rank"),
)


training_plans = sa.Table(
    "training_plans",
    runtime_persistence_metadata,
    sa.Column("plan_id", sa.Text(), primary_key=True),
    sa.Column("org_id", sa.Text(), nullable=False),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("description", sa.Text(), nullable=False),
    sa.Column("owner_id", sa.Text(), nullable=False),
    sa.Column("assigned_learners", _text_array(), nullable=False),
    sa.Column("assigned_cohorts", _text_array(), nullable=False),
    sa.Column("target_subskills", _text_array(), nullable=False),
    sa.Column("required_scenario_ids", _text_array(), nullable=False),
    sa.Column("due_date", sa.Text(), nullable=True),
    sa.Column("goal_criteria", sa.Text(), nullable=False),
    sa.Column("success_threshold", sa.Float(), nullable=False),
    sa.Column("review_cadence", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("payload_json", _jsonb(), nullable=False),
)

sa.Index("ix_training_plans_org_id_status", training_plans.c.org_id, training_plans.c.status)
sa.Index("ix_training_plans_org_id_updated_at", training_plans.c.org_id, training_plans.c.updated_at.desc())


TABLE_NAMES = tuple(runtime_persistence_metadata.tables.keys())
