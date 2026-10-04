"""relationships: асимметричные отношения между субъектами

Коммит 5 "Relationships (Phase 12)". Отношение — не одно число: у пары
(holder, subject) столько записей, сколько видов отношений менялось; каждый вид
живёт на своей именованной лестнице. Асимметрия структурная: holder→subject и
subject→holder — разные строки.

Revision ID: 0004_relationships
Revises: 0003_npcs
Create Date: 2026-10-04

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_relationships"
down_revision = "0003_npcs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relationships",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "world_instance_id",
            sa.String(length=64),
            sa.ForeignKey("world_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("holder_type", sa.String(length=16), nullable=False),
        sa.Column("holder_id", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "world_instance_id",
            "holder_type",
            "holder_id",
            "subject_type",
            "subject_id",
            "kind",
            name="uq_relationships_pair_kind",
        ),
    )
    op.create_index(
        "ix_relationships_holder", "relationships", ["world_instance_id", "holder_type", "holder_id"]
    )
    op.create_index(
        "ix_relationships_subject", "relationships", ["world_instance_id", "subject_type", "subject_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_relationships_subject", table_name="relationships")
    op.drop_index("ix_relationships_holder", table_name="relationships")
    op.drop_table("relationships")
