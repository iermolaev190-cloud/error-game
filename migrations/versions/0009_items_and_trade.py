"""Item instances and ownership for the MVP economy.

Revision ID: 0009_items_and_trade
Revises: 0008_factions
Create Date: 2026-10-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_items_and_trade"
down_revision = "0008_factions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("owner_type", sa.String(length=16), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("location_key", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_items_instance_id"),
        sa.CheckConstraint(
            "owner_type IN ('CHARACTER', 'LOCATION', 'NONE')",
            name="ck_items_owner_type",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_items_positive_quantity"),
        sa.CheckConstraint(
            "(owner_type = 'CHARACTER' AND owner_id IS NOT NULL AND location_key IS NULL) OR "
            "(owner_type = 'LOCATION' AND owner_id IS NULL AND location_key IS NOT NULL) OR "
            "(owner_type = 'NONE' AND owner_id IS NULL)",
            name="ck_items_owner_shape",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id"], ["world_instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "location_key"],
            ["location_states.world_instance_id", "location_states.key"],
            name="fk_items_location",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "owner_id"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_items_character_owner",
        ),
    )
    op.create_index(
        "ix_items_owner", "items", ["world_instance_id", "owner_type", "owner_id"]
    )
    op.create_index("ix_items_location", "items", ["world_instance_id", "location_key"])


def downgrade() -> None:
    op.drop_index("ix_items_location", table_name="items")
    op.drop_index("ix_items_owner", table_name="items")
    op.drop_table("items")