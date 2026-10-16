"""Store each Telegram user's most recently used group.

Revision ID: 0012_player_telegram_state
Revises: 0011_chat_bindings
Create Date: 2026-10-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_player_telegram_state"
down_revision = "0011_chat_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_telegram_state",
        sa.Column("telegram_user_id", sa.BigInteger(), primary_key=True),
        sa.Column("last_group_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("player_telegram_state")
