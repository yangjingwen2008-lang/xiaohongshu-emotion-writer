"""comment_reply_assistant

Revision ID: c2e4f6a8d305
Revises: b1d3f5a7c204
Create Date: 2026-07-16 23:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2e4f6a8d305"
down_revision: Union[str, Sequence[str], None] = "b1d3f5a7c204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "comment_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("publication_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_ocr_run_id", sa.String(length=36), nullable=True),
        sa.Column("author_label", sa.String(length=120), nullable=True),
        sa.Column("comment_text", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_ocr_run_id"], ["ocr_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("publication_id", "content_hash", name="uq_publication_comment_hash"),
    )
    op.create_index(op.f("ix_comment_records_publication_id"), "comment_records", ["publication_id"])
    op.create_index(op.f("ix_comment_records_source_ocr_run_id"), "comment_records", ["source_ocr_run_id"])
    op.create_index(op.f("ix_comment_records_content_hash"), "comment_records", ["content_hash"])
    op.create_table(
        "comment_reply_suggestions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("comment_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=60), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["comment_id"], ["comment_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_comment_reply_suggestions_comment_id"), "comment_reply_suggestions", ["comment_id"])
    op.create_index(op.f("ix_comment_reply_suggestions_status"), "comment_reply_suggestions", ["status"])
    op.create_index(op.f("ix_comment_reply_suggestions_input_hash"), "comment_reply_suggestions", ["input_hash"])


def downgrade() -> None:
    op.drop_index(op.f("ix_comment_reply_suggestions_input_hash"), table_name="comment_reply_suggestions")
    op.drop_index(op.f("ix_comment_reply_suggestions_status"), table_name="comment_reply_suggestions")
    op.drop_index(op.f("ix_comment_reply_suggestions_comment_id"), table_name="comment_reply_suggestions")
    op.drop_table("comment_reply_suggestions")
    op.drop_index(op.f("ix_comment_records_content_hash"), table_name="comment_records")
    op.drop_index(op.f("ix_comment_records_source_ocr_run_id"), table_name="comment_records")
    op.drop_index(op.f("ix_comment_records_publication_id"), table_name="comment_records")
    op.drop_table("comment_records")
