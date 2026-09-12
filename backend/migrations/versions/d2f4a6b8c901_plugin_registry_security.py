"""plugin_registry_security

Revision ID: d2f4a6b8c901
Revises: c91e72a4b8f0
Create Date: 2026-07-16 16:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2f4a6b8c901"
down_revision: Union[str, Sequence[str], None] = "c91e72a4b8f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugin_security_assessments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plugin_id", sa.String(length=120), nullable=False),
        sa.Column("candidate_version", sa.String(length=80), nullable=False),
        sa.Column("source_repo", sa.String(length=1000), nullable=False),
        sa.Column("pinned_ref", sa.String(length=160), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("isolation_status", sa.String(length=30), nullable=False),
        sa.Column("regression_summary", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("plugin_security_assessments") as batch_op:
        batch_op.create_index(batch_op.f("ix_plugin_security_assessments_plugin_id"), ["plugin_id"])
        batch_op.create_index(batch_op.f("ix_plugin_security_assessments_manifest_hash"), ["manifest_hash"])
        batch_op.create_index(batch_op.f("ix_plugin_security_assessments_status"), ["status"])
        batch_op.create_index(batch_op.f("ix_plugin_security_assessments_isolation_status"), ["isolation_status"])

    op.create_table(
        "plugin_registry_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plugin_id", sa.String(length=120), nullable=False),
        sa.Column("registry_version", sa.Integer(), nullable=False),
        sa.Column("plugin_version", sa.String(length=80), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("change_type", sa.String(length=30), nullable=False),
        sa.Column("source_assessment_id", sa.String(length=36), nullable=True),
        sa.Column("source_registry_version", sa.Integer(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_assessment_id"], ["plugin_security_assessments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plugin_id", "registry_version", name="uq_plugin_registry_version"),
    )
    with op.batch_alter_table("plugin_registry_versions") as batch_op:
        batch_op.create_index(batch_op.f("ix_plugin_registry_versions_plugin_id"), ["plugin_id"])
        batch_op.create_index(batch_op.f("ix_plugin_registry_versions_manifest_hash"), ["manifest_hash"])
        batch_op.create_index(batch_op.f("ix_plugin_registry_versions_status"), ["status"])
        batch_op.create_index(batch_op.f("ix_plugin_registry_versions_source_assessment_id"), ["source_assessment_id"])


def downgrade() -> None:
    with op.batch_alter_table("plugin_registry_versions") as batch_op:
        batch_op.drop_index(batch_op.f("ix_plugin_registry_versions_source_assessment_id"))
        batch_op.drop_index(batch_op.f("ix_plugin_registry_versions_status"))
        batch_op.drop_index(batch_op.f("ix_plugin_registry_versions_manifest_hash"))
        batch_op.drop_index(batch_op.f("ix_plugin_registry_versions_plugin_id"))
    op.drop_table("plugin_registry_versions")
    with op.batch_alter_table("plugin_security_assessments") as batch_op:
        batch_op.drop_index(batch_op.f("ix_plugin_security_assessments_isolation_status"))
        batch_op.drop_index(batch_op.f("ix_plugin_security_assessments_status"))
        batch_op.drop_index(batch_op.f("ix_plugin_security_assessments_manifest_hash"))
        batch_op.drop_index(batch_op.f("ix_plugin_security_assessments_plugin_id"))
    op.drop_table("plugin_security_assessments")
