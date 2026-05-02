"""create runtime persistence base tables

Revision ID: 0001_runtime_persistence_base
Revises:
Create Date: 2026-04-24 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0001_runtime_persistence_base"
down_revision = None
branch_labels = None
depends_on = None


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _text_array() -> postgresql.ARRAY:
    return postgresql.ARRAY(sa.Text())


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("learner_id", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_session_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("learner_id", name=op.f("pk_learners")),
    )

    op.create_table(
        "prompt_context_snapshots",
        sa.Column("prompt_context_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("context_hash", sa.Text(), nullable=False),
        sa.Column("skill_id", sa.Text(), nullable=False),
        sa.Column("prompt_profile", sa.Text(), nullable=False),
        sa.Column("experiment_id", sa.Text(), nullable=True),
        sa.Column("prompt_flags_json", _jsonb(), nullable=False),
        sa.Column("contracts_json", _jsonb(), nullable=False),
        sa.Column("summary_json", _jsonb(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("prompt_context_id", name=op.f("pk_prompt_context_snapshots")),
        sa.UniqueConstraint("context_hash", name=op.f("uq_prompt_context_snapshots_context_hash")),
    )

    op.create_table(
        "sessions",
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("learner_id", sa.Text(), nullable=False),
        sa.Column("prompt_context_id", sa.BigInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.learner_id"],
            name=op.f("fk_sessions_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["prompt_context_id"],
            ["prompt_context_snapshots.prompt_context_id"],
            name=op.f("fk_sessions_prompt_context_id_prompt_context_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_sessions")),
    )
    op.create_index(
        "ix_sessions_learner_id_started_at",
        "sessions",
        ["learner_id", sa.text("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_sessions_status_updated_at",
        "sessions",
        ["status", sa.text("updated_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_sessions_scenario_id_started_at",
        "sessions",
        ["scenario_id", sa.text("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_sessions_persona_id_started_at",
        "sessions",
        ["persona_id", sa.text("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_sessions_prompt_profile_experiment_id_started_at",
        "sessions",
        ["prompt_profile", "experiment_id", sa.text("started_at DESC")],
        unique=False,
    )
    op.create_index("ix_sessions_trace_id", "sessions", ["trace_id"], unique=False)

    op.create_table(
        "session_turns",
        sa.Column("turn_id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("doctor_reply", sa.Text(), nullable=False),
        sa.Column("director_phase", sa.Text(), nullable=False),
        sa.Column("director_events_json", _jsonb(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.session_id"],
            name=op.f("fk_session_turns_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("turn_id", name=op.f("pk_session_turns")),
        sa.UniqueConstraint("session_id", "turn_index", name=op.f("uq_session_turns_session_id_turn_index")),
    )

    op.create_table(
        "session_events",
        sa.Column("event_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("turn_id", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.session_id"],
            name=op.f("fk_session_events_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["session_turns.turn_id"],
            name=op.f("fk_session_events_turn_id_session_turns"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_session_events")),
        sa.UniqueConstraint("session_id", "seq", name=op.f("uq_session_events_session_id_seq")),
    )
    op.create_index(
        "ix_session_events_session_id_timestamp",
        "session_events",
        ["session_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_session_events_type_stage_timestamp",
        "session_events",
        ["type", "stage", sa.text("timestamp DESC")],
        unique=False,
    )
    op.create_index(
        "ix_session_events_trace_id_timestamp",
        "session_events",
        ["trace_id", "timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_session_events_prompt_profile_experiment_id_timestamp",
        "session_events",
        ["prompt_profile", "experiment_id", sa.text("timestamp DESC")],
        unique=False,
    )

    op.create_table(
        "session_reviews",
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("prompt_context_id", sa.BigInteger(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["prompt_context_id"],
            ["prompt_context_snapshots.prompt_context_id"],
            name=op.f("fk_session_reviews_prompt_context_id_prompt_context_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.session_id"],
            name=op.f("fk_session_reviews_session_id_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_session_reviews")),
    )
    op.create_index(
        "ix_session_reviews_overall_band_created_at",
        "session_reviews",
        ["overall_band", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_session_reviews_prompt_profile_experiment_id_created_at",
        "session_reviews",
        ["prompt_profile", "experiment_id", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_session_reviews_priority_subskills_gin",
        "session_reviews",
        ["priority_subskills"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_session_reviews_compliance_rule_ids_gin",
        "session_reviews",
        ["compliance_rule_ids"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_session_reviews_compliance_severities_gin",
        "session_reviews",
        ["compliance_severities"],
        unique=False,
        postgresql_using="gin",
    )

    op.create_table(
        "learner_progress_snapshots",
        sa.Column("progress_snapshot_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("learner_id", sa.Text(), nullable=False),
        sa.Column("source_session_id", sa.Text(), nullable=True),
        sa.Column("total_sessions", sa.Integer(), nullable=False),
        sa.Column("total_exp", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subskills_json", _jsonb(), nullable=False),
        sa.Column("weakness_clusters_json", _jsonb(), nullable=False),
        sa.Column("recent_history_json", _jsonb(), nullable=False),
        sa.Column("coach_memory_json", _jsonb(), nullable=False),
        sa.Column("payload_json", _jsonb(), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.learner_id"],
            name=op.f("fk_learner_progress_snapshots_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["sessions.session_id"],
            name=op.f("fk_learner_progress_snapshots_source_session_id_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("progress_snapshot_id", name=op.f("pk_learner_progress_snapshots")),
    )
    op.create_index(
        "ix_learner_progress_snapshots_learner_id_updated_at",
        "learner_progress_snapshots",
        ["learner_id", sa.text("updated_at DESC")],
        unique=False,
    )

    op.create_table(
        "session_recommendations",
        sa.Column("recommendation_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("progress_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("learner_id", sa.Text(), nullable=False),
        sa.Column("source_session_id", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("scenario_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.Text(), nullable=False),
        sa.Column("target_subskills", _text_array(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_id"],
            ["learners.learner_id"],
            name=op.f("fk_session_recommendations_learner_id_learners"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["progress_snapshot_id"],
            ["learner_progress_snapshots.progress_snapshot_id"],
            name="fk_session_recommendations_progress_snapshot",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["sessions.session_id"],
            name=op.f("fk_session_recommendations_source_session_id_sessions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("recommendation_id", name=op.f("pk_session_recommendations")),
        sa.UniqueConstraint(
            "progress_snapshot_id",
            "rank",
            name=op.f("uq_session_recommendations_progress_snapshot_id_rank"),
        ),
    )


def downgrade() -> None:
    op.drop_table("session_recommendations")
    op.drop_index("ix_learner_progress_snapshots_learner_id_updated_at", table_name="learner_progress_snapshots")
    op.drop_table("learner_progress_snapshots")
    op.drop_index("ix_session_reviews_compliance_severities_gin", table_name="session_reviews")
    op.drop_index("ix_session_reviews_compliance_rule_ids_gin", table_name="session_reviews")
    op.drop_index("ix_session_reviews_priority_subskills_gin", table_name="session_reviews")
    op.drop_index("ix_session_reviews_prompt_profile_experiment_id_created_at", table_name="session_reviews")
    op.drop_index("ix_session_reviews_overall_band_created_at", table_name="session_reviews")
    op.drop_table("session_reviews")
    op.drop_index("ix_session_events_prompt_profile_experiment_id_timestamp", table_name="session_events")
    op.drop_index("ix_session_events_trace_id_timestamp", table_name="session_events")
    op.drop_index("ix_session_events_type_stage_timestamp", table_name="session_events")
    op.drop_index("ix_session_events_session_id_timestamp", table_name="session_events")
    op.drop_table("session_events")
    op.drop_table("session_turns")
    op.drop_index("ix_sessions_trace_id", table_name="sessions")
    op.drop_index("ix_sessions_prompt_profile_experiment_id_started_at", table_name="sessions")
    op.drop_index("ix_sessions_persona_id_started_at", table_name="sessions")
    op.drop_index("ix_sessions_scenario_id_started_at", table_name="sessions")
    op.drop_index("ix_sessions_status_updated_at", table_name="sessions")
    op.drop_index("ix_sessions_learner_id_started_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("prompt_context_snapshots")
    op.drop_table("learners")
