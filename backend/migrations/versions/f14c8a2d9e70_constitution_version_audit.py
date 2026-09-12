"""constitution_version_audit

Revision ID: f14c8a2d9e70
Revises: e3a9c57b1d24
Create Date: 2026-07-16 00:35:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f14c8a2d9e70"
down_revision: Union[str, Sequence[str], None] = "e3a9c57b1d24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("style_training_proposals", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "editorial_constitution_version",
                sa.Integer(),
                server_default="0",
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("style_training_proposals", schema=None) as batch_op:
        batch_op.drop_column("editorial_constitution_version")
