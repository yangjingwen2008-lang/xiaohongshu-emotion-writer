"""analytics_reports

Revision ID: b1d3f5a7c204
Revises: f9c2d4e6a103
Create Date: 2026-07-16 22:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1d3f5a7c204"
down_revision: Union[str, Sequence[str], None] = "f9c2d4e6a103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("report_type", sa.String(length=20), nullable=False),
        sa.Column("publication_id", sa.String(length=36), nullable=True),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_snapshot_ids", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("confirmed_suggestion_ids", sa.JSON(), nullable=False),
        sa.Column("decision_note", sa.String(length=1000), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analytics_reports_report_type"), "analytics_reports", ["report_type"])
    op.create_index(op.f("ix_analytics_reports_publication_id"), "analytics_reports", ["publication_id"])
    op.create_index(op.f("ix_analytics_reports_period_start"), "analytics_reports", ["period_start"])
    op.create_index(op.f("ix_analytics_reports_period_end"), "analytics_reports", ["period_end"])
    op.create_index(op.f("ix_analytics_reports_status"), "analytics_reports", ["status"])
    op.create_index(op.f("ix_analytics_reports_input_hash"), "analytics_reports", ["input_hash"])


def downgrade() -> None:
    op.drop_index(op.f("ix_analytics_reports_input_hash"), table_name="analytics_reports")
    op.drop_index(op.f("ix_analytics_reports_status"), table_name="analytics_reports")
    op.drop_index(op.f("ix_analytics_reports_period_end"), table_name="analytics_reports")
    op.drop_index(op.f("ix_analytics_reports_period_start"), table_name="analytics_reports")
    op.drop_index(op.f("ix_analytics_reports_publication_id"), table_name="analytics_reports")
    op.drop_index(op.f("ix_analytics_reports_report_type"), table_name="analytics_reports")
    op.drop_table("analytics_reports")
