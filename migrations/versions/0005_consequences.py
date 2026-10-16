"""consequences: последствия действий и их причины

Коммит 6 "Consequences (Phase 13)". Последствие всегда имеет причину:
``source_event_id`` — обязательная первопричина (§14), остальные причины лежат
в ``consequence_causes`` (§26). Композитные FK на ``events (world_instance_id,
id)`` структурно запрещают ссылаться на событие чужого INSTANCE.

Revision ID: 0005_consequences
Revises: 0004_relationships
Create Date: 2026-10-04

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_consequences"
down_revision = "0004_relationships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consequences",
        sa.Column("seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column(
            "world_instance_id",
            sa.String(length=64),
            sa.ForeignKey("world_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_event_id", sa.String(length=64), nullable=False),
        sa.Column("rule_key", sa.String(length=64), nullable=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("scale", sa.String(length=16), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("trigger_kind", sa.String(length=16), nullable=False),
        sa.Column("trigger_ticks", sa.Integer(), nullable=True),
        sa.Column("trigger_event_type", sa.String(length=64), nullable=True),
        sa.Column("effect", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("due_tick", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_event_id", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_consequences_instance_id"),
        sa.UniqueConstraint(
            "world_instance_id",
            "rule_key",
            "source_event_id",
            name="uq_consequences_rule_event",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "source_event_id"],
            ["events.world_instance_id", "events.id"],
            name="fk_consequences_source_event",
        ),
    )
    op.create_index(
        "ix_consequences_due", "consequences", ["world_instance_id", "status", "due_tick"]
    )
    op.create_index(
        "ix_consequences_trigger",
        "consequences",
        ["world_instance_id", "status", "trigger_event_type"],
    )

    op.create_table(
        "consequence_causes",
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("consequence_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "consequence_id", "event_id", name="uq_consequence_causes_pair"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "consequence_id"],
            ["consequences.world_instance_id", "consequences.id"],
            name="fk_consequence_causes_consequence",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "event_id"],
            ["events.world_instance_id", "events.id"],
            name="fk_consequence_causes_event",
        ),
    )
    op.create_index(
        "ix_consequence_causes_event", "consequence_causes", ["world_instance_id", "event_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_consequence_causes_event", table_name="consequence_causes")
    op.drop_table("consequence_causes")
    op.drop_index("ix_consequences_trigger", table_name="consequences")
    op.drop_index("ix_consequences_due", table_name="consequences")
    op.drop_table("consequences")
