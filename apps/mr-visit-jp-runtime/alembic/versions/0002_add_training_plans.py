"""add training plans table

Revision ID: 0002_add_training_plans
Revises: 0001_runtime_persistence_base
Create Date: 2026-05-01 00:00:00

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_add_training_plans"
down_revision = "0001_runtime_persistence_base"
branch_labels = None
depends_on = None


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _text_array() -> postgresql.ARRAY:
    return postgresql.ARRAY(sa.Text())


def upgrade() -> None:
    op.create_table(
        "training_plans",
        sa.Column("plan_id", sa.Text(), nullable=False),
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
        sa.PrimaryKeyConstraint("plan_id", name=op.f("pk_training_plans")),
    )
    op.create_index(
        "ix_training_plans_org_id_status",
        "training_plans",
        ["org_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_training_plans_org_id_updated_at",
        "training_plans",
        ["org_id", sa.text("updated_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_training_plans_org_id_updated_at", table_name="training_plans")
    op.drop_index("ix_training_plans_org_id_status", table_name="training_plans")
    op.drop_table("training_plans")
