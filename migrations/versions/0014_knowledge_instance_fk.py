"""Enforce instance-scoped knowledge-to-information references.

Revision ID: 0014_knowledge_instance_fk
Revises: 0013_admin_users
Create Date: 2026-10-08
"""

from __future__ import annotations

from alembic import op

revision = "0014_knowledge_instance_fk"
down_revision = "0013_admin_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.create_foreign_key(
            "fk_knowledge_information_instance",
            "information",
            ["world_instance_id", "information_id"],
            ["world_instance_id", "id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.drop_constraint(
            "fk_knowledge_information_instance", type_="foreignkey"
        )
