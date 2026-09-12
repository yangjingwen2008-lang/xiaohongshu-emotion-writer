"""workflow_step_retries

Revision ID: d6f8a0b2c416
Revises: c2e4f6a8d305
Create Date: 2026-07-16 21:20:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d6f8a0b2c416"
down_revision: Union[str, Sequence[str], None] = "c2e4f6a8d305"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workflow_steps", sa.Column("input_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "workflow_steps",
        sa.Column("attempt_no", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.execute("UPDATE workflow_steps SET input_hash = idempotency_key WHERE input_hash IS NULL")
    with op.batch_alter_table("workflow_steps") as batch_op:
        batch_op.alter_column("input_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("attempt_no", existing_type=sa.Integer(), server_default=None)
        batch_op.create_index("ix_workflow_steps_input_hash", ["input_hash"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("workflow_steps") as batch_op:
        batch_op.drop_index("ix_workflow_steps_input_hash")
        batch_op.drop_column("attempt_no")
        batch_op.drop_column("input_hash")
