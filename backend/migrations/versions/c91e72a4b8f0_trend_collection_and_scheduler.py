"""trend_collection_and_scheduler

Revision ID: c91e72a4b8f0
Revises: a82d45f91c63
Create Date: 2026-07-16 11:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c91e72a4b8f0"
down_revision: Union[str, Sequence[str], None] = "a82d45f91c63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trend_refresh_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trigger", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("query_count", sa.Integer(), nullable=False),
        sa.Column("usage_credits", sa.Integer(), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("data_status", sa.String(length=30), nullable=False),
        sa.Column("request_ids", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_trend_refresh_run_idempotency"),
    )
    with op.batch_alter_table("trend_refresh_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trend_refresh_runs_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_trend_refresh_runs_trigger"), ["trigger"], unique=False)

    op.create_table(
        "manual_trend_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=240), nullable=False),
        sa.Column("source_value", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("manual_trend_sources", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_manual_trend_sources_content_hash"), ["content_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_manual_trend_sources_source_type"), ["source_type"], unique=False)

    op.create_table(
        "trend_source_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("manual_source_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("url", sa.String(length=1200), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("provider_score", sa.String(length=40), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["manual_source_id"], ["manual_trend_sources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["trend_refresh_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("trend_source_records", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trend_source_records_manual_source_id"), ["manual_source_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_trend_source_records_platform"), ["platform"], unique=False)
        batch_op.create_index(batch_op.f("ix_trend_source_records_run_id"), ["run_id"], unique=False)

    op.create_table(
        "trend_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("emotion", sa.String(length=120), nullable=False),
        sa.Column("source_ids", sa.JSON(), nullable=False),
        sa.Column("source_platforms", sa.JSON(), nullable=False),
        sa.Column("source_links", sa.JSON(), nullable=False),
        sa.Column("trend_signal", sa.String(length=80), nullable=False),
        sa.Column("trend_basis", sa.Text(), nullable=False),
        sa.Column("female_emotional_angle", sa.Text(), nullable=False),
        sa.Column("account_fit", sa.String(length=20), nullable=False),
        sa.Column("homogeneity_risk", sa.String(length=20), nullable=False),
        sa.Column("cultural_association", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("data_limitations", sa.Text(), nullable=False),
        sa.Column("rewrite_logic", sa.Text(), nullable=False),
        sa.Column("used_content_id", sa.String(length=36), nullable=True),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["trend_refresh_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["used_content_id"], ["contents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("trend_candidates", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trend_candidates_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_trend_candidates_used_content_id"), ["used_content_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("trend_candidates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trend_candidates_used_content_id"))
        batch_op.drop_index(batch_op.f("ix_trend_candidates_run_id"))
    op.drop_table("trend_candidates")
    with op.batch_alter_table("trend_source_records", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trend_source_records_run_id"))
        batch_op.drop_index(batch_op.f("ix_trend_source_records_platform"))
        batch_op.drop_index(batch_op.f("ix_trend_source_records_manual_source_id"))
    op.drop_table("trend_source_records")
    with op.batch_alter_table("manual_trend_sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_manual_trend_sources_source_type"))
        batch_op.drop_index(batch_op.f("ix_manual_trend_sources_content_hash"))
    op.drop_table("manual_trend_sources")
    with op.batch_alter_table("trend_refresh_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trend_refresh_runs_trigger"))
        batch_op.drop_index(batch_op.f("ix_trend_refresh_runs_status"))
    op.drop_table("trend_refresh_runs")
