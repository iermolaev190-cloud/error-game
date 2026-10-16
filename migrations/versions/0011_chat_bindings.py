"""Add explicit Telegram group to WORLD INSTANCE bindings.

Revision ID: 0011_chat_bindings
Revises: 0010_investigation_engine
Create Date: 2026-10-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_chat_bindings"
down_revision = "0010_investigation_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_bindings",
        sa.Column("telegram_chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "world_instance_id", name="uq_chat_bindings_world_instance"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id"],
            ["world_instances.id"],
            name="fk_chat_bindings_world_instance",
            ondelete="CASCADE",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO chat_bindings (telegram_chat_id, world_instance_id, created_at) "
            "SELECT telegram_chat_id, id, created_at FROM world_instances "
            "WHERE telegram_chat_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.drop_table("chat_bindings")
