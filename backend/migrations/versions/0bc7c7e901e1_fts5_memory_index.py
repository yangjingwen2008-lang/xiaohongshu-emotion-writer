"""fts5_memory_index

Revision ID: 0bc7c7e901e1
Revises: 668a4577ae2e
Create Date: 2026-07-15 23:58:58.214859
"""
from typing import Sequence, Union
from alembic import op


revision: str = '0bc7c7e901e1'
down_revision: Union[str, Sequence[str], None] = '668a4577ae2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS content_search_fts USING fts5(
            version_id UNINDEXED,
            content_id UNINDEXED,
            title_tokens,
            body_tokens,
            metadata_tokens,
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS content_search_fts")
