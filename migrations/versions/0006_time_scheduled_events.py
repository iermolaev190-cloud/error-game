"""World time anchors, event metadata and scheduled events.

Revision ID: 0006_time_scheduled_events
Revises: 0005_consequences
Create Date: 2026-10-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_time_scheduled_events"
down_revision = "0005_consequences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "world_instances", sa.Column("anchor_real_time", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        sa.text("UPDATE world_instances SET anchor_real_time = current_time WHERE anchor_real_time IS NULL")
    )
    with op.batch_alter_table("world_instances") as batch_op:
        batch_op.alter_column("anchor_real_time", nullable=False)
        batch_op.add_column(
            sa.Column("time_scale", sa.Float(), nullable=False, server_default="1.0")
        )
    op.add_column(
        "events",
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("knowledge", sa.Column("document_date", sa.Date(), nullable=True))
    op.create_table(
        "scheduled_events",
        sa.Column("seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("cause_event_id", sa.String(length=64), nullable=False),
        sa.Column("created_event_id", sa.String(length=64), nullable=False),
        sa.Column("trigger_kind", sa.String(length=16), nullable=False),
        sa.Column("due_tick", sa.Integer(), nullable=True),
        sa.Column("due_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_event_type", sa.String(length=64), nullable=True),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_event_id", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_scheduled_events_instance_id"),
        sa.UniqueConstraint(
            "world_instance_id", "idempotency_key", name="uq_scheduled_events_idempotency"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id"], ["world_instances.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "cause_event_id"],
            ["events.world_instance_id", "events.id"],
            name="fk_scheduled_events_cause_event",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "created_event_id"],
            ["events.world_instance_id", "events.id"],
            name="fk_scheduled_events_created_event",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "triggered_event_id"],
            ["events.world_instance_id", "events.id"],
            name="fk_scheduled_events_triggered_event",
        ),
        sa.CheckConstraint(
            "(due_tick IS NOT NULL AND due_time IS NULL) OR "
            "(due_tick IS NULL AND due_time IS NOT NULL)",
            name="ck_scheduled_events_one_due_value",
        ),
        sa.CheckConstraint(
            "(trigger_kind = 'AT_TIME' AND due_time IS NOT NULL AND due_tick IS NULL) OR "
            "(trigger_kind != 'AT_TIME' AND due_time IS NULL AND due_tick IS NOT NULL)",
            name="ck_scheduled_events_due_matches_trigger",
        ),
        sa.CheckConstraint(
            "(trigger_kind = 'ON_EVENT_TYPE' AND trigger_event_type IS NOT NULL) OR "
            "(trigger_kind != 'ON_EVENT_TYPE' AND trigger_event_type IS NULL)",
            name="ck_scheduled_events_event_trigger_type",
        ),
    )
    op.create_index(
        "ix_scheduled_events_tick", "scheduled_events", ["world_instance_id", "status", "due_tick"]
    )
    op.create_index(
        "ix_scheduled_events_time", "scheduled_events", ["world_instance_id", "status", "due_time"]
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_events_time", table_name="scheduled_events")
    op.drop_index("ix_scheduled_events_tick", table_name="scheduled_events")
    op.drop_table("scheduled_events")
    op.drop_column("knowledge", "document_date")
    op.drop_column("events", "metadata")
    with op.batch_alter_table("world_instances") as batch_op:
        batch_op.drop_column("time_scale")
        batch_op.drop_column("anchor_real_time")