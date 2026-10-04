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
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
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
    ForeignKeyConstraint(
        ["world_instance_id", "location_key"],
        ["location_states.world_instance_id", "location_states.key"],
        name="fk_characters_location",
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
