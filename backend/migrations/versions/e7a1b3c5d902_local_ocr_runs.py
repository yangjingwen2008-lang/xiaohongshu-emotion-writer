"""local_ocr_runs

Revision ID: e7a1b3c5d902
Revises: d2f4a6b8c901
Create Date: 2026-07-16 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a1b3c5d902"
down_revision: Union[str, Sequence[str], None] = "d2f4a6b8c901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ocr_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("original_filename", sa.String(length=500), nullable=False),
        sa.Column("media_type", sa.String(length=80), nullable=False),
        sa.Column("image_path", sa.String(length=1200), nullable=True),
        sa.Column("image_hash", sa.String(length=64), nullable=False),
        sa.Column("image_size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("recognized_text", sa.Text(), nullable=True),
        sa.Column("corrected_text", sa.Text(), nullable=True),
        sa.Column("lines", sa.JSON(), nullable=False),
        sa.Column("engine_metadata", sa.JSON(), nullable=False),
        sa.Column("retention_policy", sa.String(length=60), nullable=False),
        sa.Column("linked_manual_trend_source_id", sa.String(length=36), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["linked_manual_trend_source_id"], ["manual_trend_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ocr_runs") as batch_op:
        batch_op.create_index(batch_op.f("ix_ocr_runs_purpose"), ["purpose"])
        batch_op.create_index(batch_op.f("ix_ocr_runs_status"), ["status"])
        batch_op.create_index(batch_op.f("ix_ocr_runs_image_hash"), ["image_hash"])
        batch_op.create_index(batch_op.f("ix_ocr_runs_linked_manual_trend_source_id"), ["linked_manual_trend_source_id"])


def downgrade() -> None:
    with op.batch_alter_table("ocr_runs") as batch_op:
        batch_op.drop_index(batch_op.f("ix_ocr_runs_linked_manual_trend_source_id"))
        batch_op.drop_index(batch_op.f("ix_ocr_runs_image_hash"))
        batch_op.drop_index(batch_op.f("ix_ocr_runs_status"))
        batch_op.drop_index(batch_op.f("ix_ocr_runs_purpose"))
    op.drop_table("ocr_runs")
