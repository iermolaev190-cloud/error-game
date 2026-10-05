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
    UniqueConstraint(
        "world_instance_id",
        "subject_type",
        "subject_id",
        "information_id",
        name="uq_knowledge_subject_information",
    ),
    Index("ix_knowledge_subject", "world_instance_id", "subject_id"),
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
