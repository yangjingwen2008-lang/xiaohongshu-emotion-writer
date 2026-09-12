"""analytics_ocr_link

Revision ID: f9c2d4e6a103
Revises: e7a1b3c5d902
Create Date: 2026-07-16 20:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f9c2d4e6a103"
down_revision: Union[str, Sequence[str], None] = "e7a1b3c5d902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ocr_runs") as batch_op:
        batch_op.add_column(sa.Column("linked_analytics_snapshot_id", sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f("ix_ocr_runs_linked_analytics_snapshot_id"), ["linked_analytics_snapshot_id"])
        batch_op.create_foreign_key(
            "fk_ocr_runs_linked_analytics_snapshot_id",
            "analytics_snapshots",
            ["linked_analytics_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("ocr_runs") as batch_op:
        batch_op.drop_constraint("fk_ocr_runs_linked_analytics_snapshot_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_ocr_runs_linked_analytics_snapshot_id"))
        batch_op.drop_column("linked_analytics_snapshot_id")
