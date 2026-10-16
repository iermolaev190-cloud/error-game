"""Faction state, locations, and relationship visibility.

Revision ID: 0008_factions
Revises: 0007_death_action_cost
Create Date: 2026-10-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_factions"
down_revision = "0007_death_action_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "factions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_factions_instance_id"),
        sa.UniqueConstraint("world_instance_id", "key", name="uq_factions_instance_key"),
        sa.ForeignKeyConstraint(
            ["world_instance_id"], ["world_instances.id"], ondelete="CASCADE"
        ),
    )
    op.create_table(
        "faction_locations",
        sa.Column("world_instance_id", sa.String(length=64), primary_key=True),
        sa.Column("faction_id", sa.String(length=64), primary_key=True),
        sa.Column("location_key", sa.String(length=64), primary_key=True),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "faction_id"],
            ["factions.world_instance_id", "factions.id"],
            name="fk_faction_locations_faction",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "location_key"],
            ["location_states.world_instance_id", "location_states.key"],
            name="fk_faction_locations_location",
            ondelete="CASCADE",
        ),
    )
    with op.batch_alter_table("relationships") as batch_op:
        batch_op.add_column(
            sa.Column("visibility", sa.String(length=16), nullable=False, server_default="PUBLIC")
        )


def downgrade() -> None:
    with op.batch_alter_table("relationships") as batch_op:
        batch_op.drop_column("visibility")
    op.drop_table("faction_locations")
    op.drop_table("factions")