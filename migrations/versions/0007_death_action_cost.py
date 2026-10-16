"""Death events, world legacy documents, and action-cost support.

Revision ID: 0007_death_action_cost
Revises: 0006_time_scheduled_events
Create Date: 2026-10-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_death_action_cost"
down_revision = "0006_time_scheduled_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("characters") as batch_op:
        batch_op.add_column(sa.Column("death_event_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("death_cause_event_id", sa.String(length=64), nullable=True))
        batch_op.create_unique_constraint(
            "uq_characters_instance_id", ["world_instance_id", "id"]
        )
        batch_op.create_foreign_key(
            "fk_characters_death_event",
            "events",
            ["world_instance_id", "death_event_id"],
            ["world_instance_id", "id"],
        )
        batch_op.create_foreign_key(
            "fk_characters_death_cause_event",
            "events",
            ["world_instance_id", "death_cause_event_id"],
            ["world_instance_id", "id"],
        )
        batch_op.create_check_constraint(
            "ck_characters_death_references",
            "(lifecycle = 'DEAD' AND death_event_id IS NOT NULL AND death_cause_event_id IS NOT NULL) OR "
            "(lifecycle != 'DEAD' AND death_event_id IS NULL AND death_cause_event_id IS NULL)",
        )

    op.create_table(
        "legacy_items",
        sa.Column("seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("document_key", sa.String(length=64), nullable=False),
        sa.Column("location_key", sa.String(length=64), nullable=False),
        sa.Column("created_by_character_id", sa.String(length=64), nullable=False),
        sa.Column("death_event_id", sa.String(length=64), nullable=False),
        sa.Column("created_event_id", sa.String(length=64), nullable=False),
        sa.Column("content", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_legacy_items_instance_id"),
        sa.UniqueConstraint("world_instance_id", "document_key", name="uq_legacy_items_instance_key"),
        sa.ForeignKeyConstraint(
            ["world_instance_id"], ["world_instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "location_key"],
            ["location_states.world_instance_id", "location_states.key"],
            name="fk_legacy_items_location",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "created_by_character_id"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_legacy_items_creator",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "death_event_id"],
            ["events.world_instance_id", "events.id"],
            name="fk_legacy_items_death_event",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "created_event_id"],
            ["events.world_instance_id", "events.id"],
            name="fk_legacy_items_created_event",
        ),
    )
    op.create_index(
        "ix_legacy_items_location", "legacy_items", ["world_instance_id", "location_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_legacy_items_location", table_name="legacy_items")
    op.drop_table("legacy_items")
    with op.batch_alter_table("characters") as batch_op:
        batch_op.drop_constraint("ck_characters_death_references", type_="check")
        batch_op.drop_constraint("fk_characters_death_cause_event", type_="foreignkey")
        batch_op.drop_constraint("fk_characters_death_event", type_="foreignkey")
        batch_op.drop_constraint("uq_characters_instance_id", type_="unique")
        batch_op.drop_column("death_cause_event_id")
        batch_op.drop_column("death_event_id")
