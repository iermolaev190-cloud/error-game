"""npcs: NPC как субъекты мира

Коммит 4 "NPC core без AI". Знание NPC отдельной таблицы не получает: оно
живёт в существующей ``knowledge`` с ``subject_type = NPC``. В БД хранится
только instance-состояние NPC (локация, статус); имя, описание и цели — контент.

Revision ID: 0003_npcs
Revises: 0002_first_gameplay_loop
Create Date: 2026-10-04

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_npcs"
down_revision = "0002_first_gameplay_loop"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "npcs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "world_instance_id",
            sa.String(length=64),
            sa.ForeignKey("world_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("location_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "key", name="uq_npcs_instance_key"),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "location_key"],
            ["location_states.world_instance_id", "location_states.key"],
            name="fk_npcs_location",
        ),
    )
    op.create_index("ix_npcs_instance_location", "npcs", ["world_instance_id", "location_key"])


def downgrade() -> None:
    op.drop_index("ix_npcs_instance_location", table_name="npcs")
    op.drop_table("npcs")
