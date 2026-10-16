"""Minimal instance-scoped investigation engine.

Revision ID: 0010_investigation_engine
Revises: 0009_items_and_trade
Create Date: 2026-10-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_investigation_engine"
down_revision = "0009_items_and_trade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("information") as batch_op:
        batch_op.create_unique_constraint(
            "uq_information_instance_id", ["world_instance_id", "id"]
        )
    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.create_unique_constraint("uq_knowledge_instance_id", ["world_instance_id", "id"])

    op.create_table(
        "cases",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("current_question", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_cases_instance_id"),
        sa.UniqueConstraint("world_instance_id", "key", name="uq_cases_instance_key"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'CLOSED', 'ABANDONED', 'UNRESOLVED')",
            name="ck_cases_status",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id"], ["world_instances.id"], ondelete="CASCADE"
        ),
    )
    op.create_table(
        "case_questions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.String(length=1000), nullable=False),
        sa.Column("added_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_case_questions_instance_id"),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "case_id"],
            ["cases.world_instance_id", "cases.id"],
            name="fk_case_questions_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "added_by"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_case_questions_author",
        ),
    )
    op.create_index(
        "ix_case_questions_case", "case_questions", ["world_instance_id", "case_id", "created_at"]
    )

    op.create_table(
        "case_evidence_links",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("information_id", sa.String(length=64), nullable=False),
        sa.Column("knowledge_id", sa.String(length=64), nullable=True),
        sa.Column("relevance", sa.String(length=16), nullable=False),
        sa.Column("added_by", sa.String(length=64), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "world_instance_id", "id", name="uq_case_evidence_links_instance_id"
        ),
        sa.UniqueConstraint(
            "world_instance_id", "case_id", "information_id",
            name="uq_case_evidence_case_information",
        ),
        sa.CheckConstraint(
            "relevance IN ('SUPPORTING', 'CONTRADICTING', 'NEUTRAL', 'UNKNOWN')",
            name="ck_case_evidence_relevance",
        ),
        sa.CheckConstraint(
            "(knowledge_id IS NULL AND added_by IS NULL) OR "
            "(knowledge_id IS NOT NULL AND added_by IS NOT NULL)",
            name="ck_case_evidence_authorship",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "case_id"],
            ["cases.world_instance_id", "cases.id"],
            name="fk_case_evidence_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "information_id"],
            ["information.world_instance_id", "information.id"],
            name="fk_case_evidence_information",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "knowledge_id"],
            ["knowledge.world_instance_id", "knowledge.id"],
            name="fk_case_evidence_knowledge",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "added_by"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_case_evidence_author",
        ),
    )
    op.create_index("ix_case_evidence_case", "case_evidence_links", ["world_instance_id", "case_id"])

    op.create_table(
        "case_theories",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("author_id", sa.String(length=64), nullable=False),
        sa.Column("claim", sa.String(length=1000), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_case_theories_instance_id"),
        sa.CheckConstraint(
            "confidence IN ('SPECULATIVE', 'PLAUSIBLE', 'SUPPORTED', 'CONFIRMED')",
            name="ck_case_theories_confidence",
        ),
        sa.CheckConstraint(
            "visibility IN ('PRIVATE', 'CASE_SHARED')", name="ck_case_theories_visibility"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'REJECTED', 'CONFIRMED', 'UNRESOLVED')",
            name="ck_case_theories_status",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "case_id"],
            ["cases.world_instance_id", "cases.id"],
            name="fk_case_theories_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "author_id"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_case_theories_author",
        ),
    )
    op.create_index("ix_case_theories_case", "case_theories", ["world_instance_id", "case_id"])

    op.create_table(
        "case_theory_evidence_links",
        sa.Column("world_instance_id", sa.String(length=64), primary_key=True),
        sa.Column("theory_id", sa.String(length=64), primary_key=True),
        sa.Column("evidence_link_id", sa.String(length=64), primary_key=True),
        sa.Column("stance", sa.String(length=16), nullable=False),
        sa.Column("added_by", sa.String(length=64), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "stance IN ('SUPPORTING', 'CONTRADICTING')", name="ck_case_theory_evidence_stance"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "theory_id"],
            ["case_theories.world_instance_id", "case_theories.id"],
            name="fk_case_theory_evidence_theory",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "evidence_link_id"],
            ["case_evidence_links.world_instance_id", "case_evidence_links.id"],
            name="fk_case_theory_evidence_link",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "added_by"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_case_theory_evidence_author",
        ),
    )

    op.create_table(
        "case_contradiction_links",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_a_id", sa.String(length=64), nullable=False),
        sa.Column("evidence_b_id", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=False),
        sa.Column("marked_by", sa.String(length=64), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "world_instance_id", "id", name="uq_case_contradictions_instance_id"
        ),
        sa.CheckConstraint(
            "evidence_a_id != evidence_b_id", name="ck_case_contradiction_distinct_evidence"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "case_id"],
            ["cases.world_instance_id", "cases.id"],
            name="fk_case_contradictions_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "evidence_a_id"],
            ["case_evidence_links.world_instance_id", "case_evidence_links.id"],
            name="fk_case_contradictions_evidence_a",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "evidence_b_id"],
            ["case_evidence_links.world_instance_id", "case_evidence_links.id"],
            name="fk_case_contradictions_evidence_b",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "marked_by"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_case_contradictions_author",
        ),
    )

    op.create_table(
        "case_suspect_links",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("marked_by", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_case_suspects_instance_id"),
        sa.UniqueConstraint(
            "world_instance_id", "case_id", "subject_type", "subject_id",
            name="uq_case_suspects_subject",
        ),
        sa.CheckConstraint(
            "subject_type IN ('CHARACTER', 'NPC', 'FACTION')",
            name="ck_case_suspects_subject_type",
        ),
        sa.CheckConstraint(
            "status IN ('SUSPECTED', 'CLEARED', 'CONFIRMED', 'UNKNOWN')",
            name="ck_case_suspects_status",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "case_id"],
            ["cases.world_instance_id", "cases.id"],
            name="fk_case_suspects_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "marked_by"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_case_suspects_author",
        ),
    )

    op.create_table(
        "case_notes",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("world_instance_id", sa.String(length=64), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("author_id", sa.String(length=64), nullable=False),
        sa.Column("text", sa.String(length=2000), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("world_instance_id", "id", name="uq_case_notes_instance_id"),
        sa.CheckConstraint(
            "visibility IN ('PRIVATE', 'CASE_SHARED')", name="ck_case_notes_visibility"
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "case_id"],
            ["cases.world_instance_id", "cases.id"],
            name="fk_case_notes_case",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["world_instance_id", "author_id"],
            ["characters.world_instance_id", "characters.id"],
            name="fk_case_notes_author",
        ),
    )
    op.create_index("ix_case_notes_case", "case_notes", ["world_instance_id", "case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_notes_case", table_name="case_notes")
    op.drop_table("case_notes")
    op.drop_table("case_suspect_links")
    op.drop_table("case_contradiction_links")
    op.drop_table("case_theory_evidence_links")
    op.drop_index("ix_case_theories_case", table_name="case_theories")
    op.drop_table("case_theories")
    op.drop_index("ix_case_evidence_case", table_name="case_evidence_links")
    op.drop_table("case_evidence_links")
    op.drop_index("ix_case_questions_case", table_name="case_questions")
    op.drop_table("case_questions")
    op.drop_table("cases")
    with op.batch_alter_table("knowledge") as batch_op:
        batch_op.drop_constraint("uq_knowledge_instance_id", type_="unique")
    with op.batch_alter_table("information") as batch_op:
        batch_op.drop_constraint("uq_information_instance_id", type_="unique")