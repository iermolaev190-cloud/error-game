"""first gameplay loop: characters, location states, information, knowledge

Коммит 2 "Первый игровой цикл".

Revision ID: 0002_first_gameplay_loop
Revises: 0001_world_foundation
Create Date: 2026-10-04

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_first_gameplay_loop"
down_revision = "0001_world_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "world_instances",
        sa.Column("content_version", sa.String(length=32), nullable=False, server_default="v1"),
    )

    op.create_table(
        "location_states",
        sa.Column(
            "world_instance_id",
            sa.String(length=64),
            sa.ForeignKey("world_instances.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("discovery_state", sa.String(length=16), nullable=False),
        sa.Column("first_visited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "world_instance_id",
            sa.String(length=64),
            sa.ForeignKey("world_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("player_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("lifecycle", sa.String(length=16), nullable=False),
        sa.Column("activity", sa.String(length=16), nullable=False),
        sa.Column("location_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "location_key"],
            ["location_states.world_instance_id", "location_states.key"],
            name="fk_characters_location",
        ),
    )
    op.create_index(
        "ix_characters_instance_player", "characters", ["world_instance_id", "player_id"]
    )

    op.create_table(
        "information",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "world_instance_id",
            sa.String(length=64),
            sa.ForeignKey("world_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("location_key", sa.String(length=64), nullable=False),
        sa.Column("discovery_state", sa.String(length=16), nullable=False),
        sa.Column("discovered_by", sa.String(length=64), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "key", name="uq_information_instance_key"),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "location_key"],
            ["location_states.world_instance_id", "location_states.key"],
            name="fk_information_location",
        ),
    )
    op.create_index("ix_information_world_instance_id", "information", ["world_instance_id"])

    op.create_table(
        "knowledge",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "world_instance_id",
            sa.String(length=64),
            sa.ForeignKey("world_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column(
            "information_id",
            sa.String(length=64),
            sa.ForeignKey("information.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim", sa.String(length=1000), nullable=False),
        sa.Column("claim_type", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "world_instance_id",
            "subject_type",
            "subject_id",
            "information_id",
            name="uq_knowledge_subject_information",
        ),
    )
    op.create_index("ix_knowledge_subject", "knowledge", ["world_instance_id", "subject_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_subject", table_name="knowledge")
    op.drop_table("knowledge")
    op.drop_index("ix_information_world_instance_id", table_name="information")
    op.drop_table("information")
    op.drop_index("ix_characters_instance_player", table_name="characters")
    op.drop_table("characters")
    op.drop_table("location_states")
    op.drop_column("world_instances", "content_version")
