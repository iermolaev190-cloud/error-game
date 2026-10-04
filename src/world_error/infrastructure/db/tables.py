"""Схема БД коммита 1.

Одна и та же ``metadata`` используется и миграциями Alembic, и тестами, поэтому
схема не может разойтись между ними.

У ``events`` есть технический ``seq`` — порядок поступления событий в журнал.
Он не является частью доменной модели события.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
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
