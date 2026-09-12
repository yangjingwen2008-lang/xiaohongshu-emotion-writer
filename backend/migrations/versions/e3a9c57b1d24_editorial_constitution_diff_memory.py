"""editorial_constitution_diff_memory

Revision ID: e3a9c57b1d24
Revises: 0bc7c7e901e1
Create Date: 2026-07-16 00:20:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3a9c57b1d24"
down_revision: Union[str, Sequence[str], None] = "0bc7c7e901e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "editorial_constitution_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sections", sa.JSON(), nullable=False),
        sa.Column("change_type", sa.String(length=30), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=True),
        sa.Column("change_note", sa.String(length=500), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version", name="uq_editorial_constitution_version"),
    )
    op.create_table(
        "diff_memory_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pattern_type", sa.String(length=50), nullable=False),
        sa.Column("rule_text", sa.String(length=500), nullable=False),
        sa.Column("rule_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("profile_version_id", sa.String(length=36), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_version_id"],
            ["style_profile_versions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_hash", name="uq_diff_memory_rule_hash"),
    )
    with op.batch_alter_table("diff_memory_candidates", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_diff_memory_candidates_pattern_type"),
            ["pattern_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_diff_memory_candidates_status"),
            ["status"],
            unique=False,
        )
    with op.batch_alter_table("style_profile_versions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("source_diff_candidate_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("diff_memory_candidates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_diff_memory_candidates_status"))
        batch_op.drop_index(batch_op.f("ix_diff_memory_candidates_pattern_type"))
    op.drop_table("diff_memory_candidates")
    with op.batch_alter_table("style_profile_versions", schema=None) as batch_op:
        batch_op.drop_column("source_diff_candidate_id")
    op.drop_table("editorial_constitution_versions")
