"""external_checks_and_manual_sources

Revision ID: a82d45f91c63
Revises: f14c8a2d9e70
Create Date: 2026-07-16 01:10:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a82d45f91c63"
down_revision: Union[str, Sequence[str], None] = "f14c8a2d9e70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "external_check_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("content_id", sa.String(length=36), nullable=False),
        sa.Column("check_type", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("query_count", sa.Integer(), nullable=False),
        sa.Column("usage_credits", sa.Integer(), nullable=True),
        sa.Column("covered_sources", sa.JSON(), nullable=False),
        sa.Column("unavailable_sources", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.JSON(), nullable=False),
        sa.Column("request_ids", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("external_check_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_external_check_runs_content_id"), ["content_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_external_check_runs_check_type"), ["check_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_external_check_runs_status"), ["status"], unique=False)

    op.create_table(
        "manual_originality_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("content_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=240), nullable=False),
        sa.Column("source_value", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("manual_originality_sources", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_manual_originality_sources_content_id"), ["content_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_manual_originality_sources_source_type"), ["source_type"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("manual_originality_sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_manual_originality_sources_source_type"))
        batch_op.drop_index(batch_op.f("ix_manual_originality_sources_content_id"))
    op.drop_table("manual_originality_sources")
    with op.batch_alter_table("external_check_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_external_check_runs_status"))
        batch_op.drop_index(batch_op.f("ix_external_check_runs_check_type"))
        batch_op.drop_index(batch_op.f("ix_external_check_runs_content_id"))
    op.drop_table("external_check_runs")
