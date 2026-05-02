"""add org_id columns to sessions, learners, learner_progress_snapshots, session_events

Revision ID: 0003_add_org_id_to_tables
Revises: 0002_add_training_plans
Create Date: 2026-05-01

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_add_org_id_to_tables"
down_revision = "0002_add_training_plans"
branch_labels = None
depends_on = None

SENTINEL_ORG_ID = "__unscoped__"


def _add_org_id_column(table_name: str, extra_indexes: list[list[str]] | None = None) -> None:
    op.add_column(table_name, sa.Column("org_id", sa.Text(), nullable=True))
    op.execute(
        f"UPDATE {table_name} SET org_id = '{SENTINEL_ORG_ID}' WHERE org_id IS NULL"
    )
    op.alter_column(table_name, "org_id", nullable=False)
    if extra_indexes:
        for index_spec in extra_indexes:
            op.create_index(
                index_spec[0],
                table_name,
                index_spec[1:],
                unique=False,
            )


def _drop_org_id_column(table_name: str, index_names: list[str]) -> None:
    for idx_name in index_names:
        op.drop_index(idx_name, table_name=table_name)
    op.drop_column(table_name, "org_id")


def upgrade() -> None:
    _add_org_id_column(
        "sessions",
        [["ix_sessions_org_id_started_at", "org_id", sa.text("started_at DESC")]],
    )
    _add_org_id_column(
        "learners",
        [["ix_learners_org_id_learner_id", "org_id", "learner_id"]],
    )
    _add_org_id_column(
        "learner_progress_snapshots",
        [["ix_learner_progress_snapshots_org_id_updated_at", "org_id", sa.text("updated_at DESC")]],
    )
    _add_org_id_column(
        "session_events",
        [["ix_session_events_org_id_timestamp", "org_id", "timestamp"]],
    )


def downgrade() -> None:
    _drop_org_id_column("session_events", ["ix_session_events_org_id_timestamp"])
    _drop_org_id_column("learner_progress_snapshots", ["ix_learner_progress_snapshots_org_id_updated_at"])
    _drop_org_id_column("learners", ["ix_learners_org_id_learner_id"])
    _drop_org_id_column("sessions", ["ix_sessions_org_id_started_at"])
