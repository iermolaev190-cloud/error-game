"""Схема БД.

Одна и та же ``metadata`` используется и миграциями Alembic, и тестами, поэтому
схема не может разойтись между ними.

Принципы:
* всё изменяемое игровое состояние принадлежит WORLD INSTANCE
  (``world_instance_id`` + FK на ``world_instances``);
* глобальные определения контента в БД не дублируются — они живут в ``content/``;
* композитные FK ``(world_instance_id, location_key) → location_states``
  структурно запрещают ссылаться на локацию чужого инстанса;
* у ``events`` есть технический ``seq`` — порядок поступления событий в журнал.
Он не является частью доменной модели события.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Float,
)

metadata = MetaData()

world_instances = Table(
    "world_instances",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("telegram_chat_id", BigInteger, nullable=False),
    Column("seed", BigInteger, nullable=False),
    Column("content_version", String(32), nullable=False, server_default="v1"),
    Column("environment", String(16), nullable=False),
    Column("lifecycle", String(16), nullable=False),
    Column("current_time", DateTime(timezone=True), nullable=False),
    Column("anchor_real_time", DateTime(timezone=True), nullable=False),
    Column("time_scale", Float, nullable=False, server_default="1.0"),
    Column("world_tick", Integer, nullable=False),
    Column("state_version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

chat_bindings = Table(
    "chat_bindings",
    metadata,
    Column("telegram_chat_id", BigInteger, primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

player_telegram_state = Table(
    "player_telegram_state",
    metadata,
    Column("telegram_user_id", BigInteger, primary_key=True),
    Column("last_group_chat_id", BigInteger, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

events = Table(
    "events",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("type", String(64), nullable=False),
    Column("actor", String(128), nullable=True),
    Column("target", String(128), nullable=True),
    Column("cause", String(255), nullable=True),
    Column("payload", JSON, nullable=False),
    Column("metadata", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("executed_at", DateTime(timezone=True), nullable=True),
    Column("result", String(64), nullable=True),
    UniqueConstraint("world_instance_id", "id", name="uq_events_instance_event"),
)

location_states = Table(
    "location_states",
    metadata,
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("key", String(64), primary_key=True),
    Column("discovery_state", String(16), nullable=False),
    Column("first_visited_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

characters = Table(
    "characters",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("player_id", String(64), nullable=False),
    Column("name", String(128), nullable=False),
    Column("lifecycle", String(16), nullable=False),
    Column("activity", String(16), nullable=False),
    Column("location_key", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("death_event_id", String(64), nullable=True),
    Column("death_cause_event_id", String(64), nullable=True),
    UniqueConstraint("world_instance_id", "id", name="uq_characters_instance_id"),
    ForeignKeyConstraint(
        ["world_instance_id", "location_key"],
        ["location_states.world_instance_id", "location_states.key"],
        name="fk_characters_location",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "death_event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_characters_death_event",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "death_cause_event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_characters_death_cause_event",
    ),
    CheckConstraint(
        "(lifecycle = 'DEAD' AND death_event_id IS NOT NULL AND death_cause_event_id IS NOT NULL) OR "
        "(lifecycle != 'DEAD' AND death_event_id IS NULL AND death_cause_event_id IS NULL)",
        name="ck_characters_death_references",
    ),
    Index("ix_characters_instance_player", "world_instance_id", "player_id"),
)

information = Table(
    "information",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("key", String(64), nullable=False),
    Column("location_key", String(64), nullable=False),
    Column("discovery_state", String(16), nullable=False),
    Column("discovered_by", String(64), nullable=True),
    Column("discovered_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_information_instance_id"),
    UniqueConstraint("world_instance_id", "key", name="uq_information_instance_key"),
    ForeignKeyConstraint(
        ["world_instance_id", "location_key"],
        ["location_states.world_instance_id", "location_states.key"],
        name="fk_information_location",
    ),
)

knowledge = Table(
    "knowledge",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("subject_type", String(16), nullable=False),
    Column("subject_id", String(64), nullable=False),
    Column(
        "information_id",
        String(64),
        ForeignKey("information.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("claim", String(1000), nullable=False),
    Column("claim_type", String(16), nullable=False),
    Column("source", String(32), nullable=False),
    Column("source_ref", String(64), nullable=True),
    Column("confidence", String(16), nullable=False),
    Column("acquired_at", DateTime(timezone=True), nullable=False),
    Column("document_date", Date, nullable=True),
    UniqueConstraint("world_instance_id", "id", name="uq_knowledge_instance_id"),
    UniqueConstraint(
        "world_instance_id",
        "subject_type",
        "subject_id",
        "information_id",
        name="uq_knowledge_subject_information",
    ),
    Index("ix_knowledge_subject", "world_instance_id", "subject_id"),
)

cases = Table(
    "cases",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("key", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("current_question", String(1000), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_cases_instance_id"),
    UniqueConstraint("world_instance_id", "key", name="uq_cases_instance_key"),
    CheckConstraint(
        "status IN ('OPEN', 'CLOSED', 'ABANDONED', 'UNRESOLVED')",
        name="ck_cases_status",
    ),
)

case_questions = Table(
    "case_questions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("world_instance_id", String(64), nullable=False),
    Column("case_id", String(64), nullable=False),
    Column("text", String(1000), nullable=False),
    Column("added_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_case_questions_instance_id"),
    ForeignKeyConstraint(
        ["world_instance_id", "case_id"],
        ["cases.world_instance_id", "cases.id"],
        name="fk_case_questions_case",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "added_by"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_case_questions_author",
    ),
    Index("ix_case_questions_case", "world_instance_id", "case_id", "created_at"),
)

case_evidence_links = Table(
    "case_evidence_links",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("world_instance_id", String(64), nullable=False),
    Column("case_id", String(64), nullable=False),
    Column("information_id", String(64), nullable=False),
    Column("knowledge_id", String(64), nullable=True),
    Column("relevance", String(16), nullable=False),
    Column("added_by", String(64), nullable=True),
    Column("added_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_case_evidence_links_instance_id"),
    UniqueConstraint(
        "world_instance_id", "case_id", "information_id", name="uq_case_evidence_case_information"
    ),
    CheckConstraint(
        "relevance IN ('SUPPORTING', 'CONTRADICTING', 'NEUTRAL', 'UNKNOWN')",
        name="ck_case_evidence_relevance",
    ),
    CheckConstraint(
        "(knowledge_id IS NULL AND added_by IS NULL) OR "
        "(knowledge_id IS NOT NULL AND added_by IS NOT NULL)",
        name="ck_case_evidence_authorship",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "case_id"],
        ["cases.world_instance_id", "cases.id"],
        name="fk_case_evidence_case",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "information_id"],
        ["information.world_instance_id", "information.id"],
        name="fk_case_evidence_information",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "knowledge_id"],
        ["knowledge.world_instance_id", "knowledge.id"],
        name="fk_case_evidence_knowledge",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "added_by"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_case_evidence_author",
    ),
    Index("ix_case_evidence_case", "world_instance_id", "case_id"),
)

case_theories = Table(
    "case_theories",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("world_instance_id", String(64), nullable=False),
    Column("case_id", String(64), nullable=False),
    Column("author_id", String(64), nullable=False),
    Column("claim", String(1000), nullable=False),
    Column("confidence", String(16), nullable=False),
    Column("visibility", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_case_theories_instance_id"),
    CheckConstraint(
        "confidence IN ('SPECULATIVE', 'PLAUSIBLE', 'SUPPORTED', 'CONFIRMED')",
        name="ck_case_theories_confidence",
    ),
    CheckConstraint(
        "visibility IN ('PRIVATE', 'CASE_SHARED')", name="ck_case_theories_visibility"
    ),
    CheckConstraint(
        "status IN ('ACTIVE', 'REJECTED', 'CONFIRMED', 'UNRESOLVED')",
        name="ck_case_theories_status",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "case_id"],
        ["cases.world_instance_id", "cases.id"],
        name="fk_case_theories_case",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "author_id"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_case_theories_author",
    ),
    Index("ix_case_theories_case", "world_instance_id", "case_id"),
)

case_theory_evidence_links = Table(
    "case_theory_evidence_links",
    metadata,
    Column("world_instance_id", String(64), primary_key=True),
    Column("theory_id", String(64), primary_key=True),
    Column("evidence_link_id", String(64), primary_key=True),
    Column("stance", String(16), nullable=False),
    Column("added_by", String(64), nullable=False),
    Column("added_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "stance IN ('SUPPORTING', 'CONTRADICTING')", name="ck_case_theory_evidence_stance"
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "theory_id"],
        ["case_theories.world_instance_id", "case_theories.id"],
        name="fk_case_theory_evidence_theory",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "evidence_link_id"],
        ["case_evidence_links.world_instance_id", "case_evidence_links.id"],
        name="fk_case_theory_evidence_link",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "added_by"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_case_theory_evidence_author",
    ),
)

case_contradiction_links = Table(
    "case_contradiction_links",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("world_instance_id", String(64), nullable=False),
    Column("case_id", String(64), nullable=False),
    Column("evidence_a_id", String(64), nullable=False),
    Column("evidence_b_id", String(64), nullable=False),
    Column("note", String(1000), nullable=False),
    Column("marked_by", String(64), nullable=False),
    Column("marked_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_case_contradictions_instance_id"),
    CheckConstraint("evidence_a_id != evidence_b_id", name="ck_case_contradiction_distinct_evidence"),
    ForeignKeyConstraint(
        ["world_instance_id", "case_id"],
        ["cases.world_instance_id", "cases.id"],
        name="fk_case_contradictions_case",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "evidence_a_id"],
        ["case_evidence_links.world_instance_id", "case_evidence_links.id"],
        name="fk_case_contradictions_evidence_a",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "evidence_b_id"],
        ["case_evidence_links.world_instance_id", "case_evidence_links.id"],
        name="fk_case_contradictions_evidence_b",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "marked_by"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_case_contradictions_author",
    ),
)

case_suspect_links = Table(
    "case_suspect_links",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("world_instance_id", String(64), nullable=False),
    Column("case_id", String(64), nullable=False),
    Column("subject_type", String(16), nullable=False),
    Column("subject_id", String(64), nullable=False),
    Column("reason", String(1000), nullable=False),
    Column("marked_by", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("marked_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_case_suspects_instance_id"),
    UniqueConstraint(
        "world_instance_id", "case_id", "subject_type", "subject_id", name="uq_case_suspects_subject"
    ),
    CheckConstraint(
        "subject_type IN ('CHARACTER', 'NPC', 'FACTION')", name="ck_case_suspects_subject_type"
    ),
    CheckConstraint(
        "status IN ('SUSPECTED', 'CLEARED', 'CONFIRMED', 'UNKNOWN')",
        name="ck_case_suspects_status",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "case_id"],
        ["cases.world_instance_id", "cases.id"],
        name="fk_case_suspects_case",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "marked_by"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_case_suspects_author",
    ),
)

case_notes = Table(
    "case_notes",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("world_instance_id", String(64), nullable=False),
    Column("case_id", String(64), nullable=False),
    Column("author_id", String(64), nullable=False),
    Column("text", String(2000), nullable=False),
    Column("visibility", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_case_notes_instance_id"),
    CheckConstraint(
        "visibility IN ('PRIVATE', 'CASE_SHARED')", name="ck_case_notes_visibility"
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "case_id"],
        ["cases.world_instance_id", "cases.id"],
        name="fk_case_notes_case",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "author_id"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_case_notes_author",
    ),
    Index("ix_case_notes_case", "world_instance_id", "case_id"),
)

npcs = Table(
    "npcs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("key", String(64), nullable=False),
    Column("location_key", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "key", name="uq_npcs_instance_key"),
    ForeignKeyConstraint(
        ["world_instance_id", "location_key"],
        ["location_states.world_instance_id", "location_states.key"],
        name="fk_npcs_location",
    ),
    Index("ix_npcs_instance_location", "world_instance_id", "location_key"),
)

factions = Table(
    "factions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("key", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_factions_instance_id"),
    UniqueConstraint("world_instance_id", "key", name="uq_factions_instance_key"),
)

faction_locations = Table(
    "faction_locations",
    metadata,
    Column("world_instance_id", String(64), primary_key=True),
    Column("faction_id", String(64), primary_key=True),
    Column("location_key", String(64), primary_key=True),
    ForeignKeyConstraint(
        ["world_instance_id", "faction_id"],
        ["factions.world_instance_id", "factions.id"],
        name="fk_faction_locations_faction",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "location_key"],
        ["location_states.world_instance_id", "location_states.key"],
        name="fk_faction_locations_location",
        ondelete="CASCADE",
    ),
)

relationships = Table(
    "relationships",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("holder_type", String(16), nullable=False),
    Column("holder_id", String(64), nullable=False),
    Column("subject_type", String(16), nullable=False),
    Column("subject_id", String(64), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("level", String(16), nullable=False),
    Column("visibility", String(16), nullable=False, server_default="PUBLIC"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "world_instance_id",
        "holder_type",
        "holder_id",
        "subject_type",
        "subject_id",
        "kind",
        name="uq_relationships_pair_kind",
    ),
    Index("ix_relationships_holder", "world_instance_id", "holder_type", "holder_id"),
    Index("ix_relationships_subject", "world_instance_id", "subject_type", "subject_id"),
)

legacy_items = Table(
    "legacy_items",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False),
    Column("world_instance_id", String(64), nullable=False),
    Column("document_key", String(64), nullable=False),
    Column("location_key", String(64), nullable=False),
    Column("created_by_character_id", String(64), nullable=False),
    Column("death_event_id", String(64), nullable=False),
    Column("created_event_id", String(64), nullable=False),
    Column("content", String(2000), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_legacy_items_instance_id"),
    UniqueConstraint("world_instance_id", "document_key", name="uq_legacy_items_instance_key"),
    ForeignKeyConstraint(
        ["world_instance_id"],
        ["world_instances.id"],
        name="fk_legacy_items_instance",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "location_key"],
        ["location_states.world_instance_id", "location_states.key"],
        name="fk_legacy_items_location",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "created_by_character_id"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_legacy_items_creator",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "death_event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_legacy_items_death_event",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "created_event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_legacy_items_created_event",
    ),
    Index("ix_legacy_items_location", "world_instance_id", "location_key"),
)

items = Table(
    "items",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("key", String(64), nullable=False),
    Column("owner_type", String(16), nullable=False),
    Column("owner_id", String(64), nullable=True),
    Column("location_key", String(64), nullable=True),
    Column("quantity", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("world_instance_id", "id", name="uq_items_instance_id"),
    CheckConstraint(
        "owner_type IN ('CHARACTER', 'LOCATION', 'NONE')",
        name="ck_items_owner_type",
    ),
    CheckConstraint(
        "quantity > 0",
        name="ck_items_positive_quantity",
    ),
    CheckConstraint(
        "(owner_type = 'CHARACTER' AND owner_id IS NOT NULL AND location_key IS NULL) OR "
        "(owner_type = 'LOCATION' AND owner_id IS NULL AND location_key IS NOT NULL) OR "
        "(owner_type = 'NONE' AND owner_id IS NULL)",
        name="ck_items_owner_shape",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "location_key"],
        ["location_states.world_instance_id", "location_states.key"],
        name="fk_items_location",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "owner_id"],
        ["characters.world_instance_id", "characters.id"],
        name="fk_items_character_owner",
    ),
    Index("ix_items_owner", "world_instance_id", "owner_type", "owner_id"),
    Index("ix_items_location", "world_instance_id", "location_key"),
)

consequences = Table(
    "consequences",
    metadata,
    # seq — порядок поступления (FIFO-детерминизм обработки), id — доменный ключ.
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("source_event_id", String(64), nullable=False),
    Column("rule_key", String(64), nullable=True),
    Column("type", String(16), nullable=False),
    Column("scale", String(16), nullable=False),
    Column("visibility", String(16), nullable=False),
    Column("trigger_kind", String(16), nullable=False),
    Column("trigger_ticks", Integer, nullable=True),
    Column("trigger_event_type", String(64), nullable=True),
    Column("effect", String(32), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("status", String(16), nullable=False),
    Column("due_tick", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=True),
    Column("applied_event_id", String(64), nullable=True),
    UniqueConstraint("world_instance_id", "id", name="uq_consequences_instance_id"),
    # Одно правило не может сработать на одно и то же событие дважды:
    # материализация правил идемпотентна на уровне схемы.
    UniqueConstraint(
        "world_instance_id",
        "rule_key",
        "source_event_id",
        name="uq_consequences_rule_event",
    ),
    # Причина обязана существовать и принадлежать тому же INSTANCE (§14).
    ForeignKeyConstraint(
        ["world_instance_id", "source_event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_consequences_source_event",
    ),
    Index("ix_consequences_due", "world_instance_id", "status", "due_tick"),
    Index(
        "ix_consequences_trigger",
        "world_instance_id",
        "status",
        "trigger_event_type",
    ),
)

consequence_causes = Table(
    "consequence_causes",
    metadata,
    Column("world_instance_id", String(64), nullable=False),
    Column("consequence_id", String(64), nullable=False),
    Column("event_id", String(64), nullable=False),
    Column("origin", String(16), nullable=False),
    Column("position", Integer, nullable=False),
    # §26: причин может быть несколько — отсюда и отдельная таблица.
    UniqueConstraint("consequence_id", "event_id", name="uq_consequence_causes_pair"),
    ForeignKeyConstraint(
        ["world_instance_id", "consequence_id"],
        ["consequences.world_instance_id", "consequences.id"],
        name="fk_consequence_causes_consequence",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_consequence_causes_event",
    ),
    Index(
        "ix_consequence_causes_event",
        "world_instance_id",
        "event_id",
    ),
)

scheduled_events = Table(
    "scheduled_events",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=True),
    Column("id", String(64), nullable=False),
    Column(
        "world_instance_id",
        String(64),
        ForeignKey("world_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("cause_event_id", String(64), nullable=False),
    Column("created_event_id", String(64), nullable=False),
    Column("trigger_kind", String(16), nullable=False),
    Column("due_tick", Integer, nullable=True),
    Column("due_time", DateTime(timezone=True), nullable=True),
    Column("trigger_event_type", String(64), nullable=True),
    Column("event_key", String(128), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("metadata", JSON, nullable=False),
    Column("status", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=True),
    Column("triggered_event_id", String(64), nullable=True),
    UniqueConstraint("world_instance_id", "id", name="uq_scheduled_events_instance_id"),
    UniqueConstraint(
        "world_instance_id", "idempotency_key", name="uq_scheduled_events_idempotency"
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "cause_event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_scheduled_events_cause_event",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "created_event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_scheduled_events_created_event",
    ),
    ForeignKeyConstraint(
        ["world_instance_id", "triggered_event_id"],
        ["events.world_instance_id", "events.id"],
        name="fk_scheduled_events_triggered_event",
    ),
    CheckConstraint(
        "(due_tick IS NOT NULL AND due_time IS NULL) OR "
        "(due_tick IS NULL AND due_time IS NOT NULL)",
        name="ck_scheduled_events_one_due_value",
    ),
    CheckConstraint(
        "(trigger_kind = 'AT_TIME' AND due_time IS NOT NULL AND due_tick IS NULL) OR "
        "(trigger_kind != 'AT_TIME' AND due_time IS NULL AND due_tick IS NOT NULL)",
        name="ck_scheduled_events_due_matches_trigger",
    ),
    CheckConstraint(
        "(trigger_kind = 'ON_EVENT_TYPE' AND trigger_event_type IS NOT NULL) OR "
        "(trigger_kind != 'ON_EVENT_TYPE' AND trigger_event_type IS NULL)",
        name="ck_scheduled_events_event_trigger_type",
    ),
    Index("ix_scheduled_events_tick", "world_instance_id", "status", "due_tick"),
    Index("ix_scheduled_events_time", "world_instance_id", "status", "due_time"),
)
