"""world foundation: world_instances and events

Коммит 1 "Фундамент": минимальные таблицы — инстанс мира и append-only журнал событий.
Сущности персонажей, локаций, знаний и т.д. появятся в следующих миграциях.

Revision ID: 0001_world_foundation
Revises:
Create Date: 2026-10-04

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_world_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_instances",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("lifecycle", sa.String(length=16), nullable=False),
        sa.Column("current_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("world_tick", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "events",
        sa.Column("seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column(
            "world_instance_id",
            sa.String(length=64),
            sa.ForeignKey("world_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=True),
        sa.Column("target", sa.String(length=128), nullable=True),
        sa.Column("cause", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_events_instance_event"),
    )
    op.create_index("ix_events_world_instance_id", "events", ["world_instance_id"])


def downgrade() -> None:
    op.drop_index("ix_events_world_instance_id", table_name="events")
    op.drop_table("events")
    op.drop_table("world_instances")
