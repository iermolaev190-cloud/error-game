"""Создание engine и фабрики сессий.

Локально — SQLite, прод-цель — PostgreSQL (решение по стеку коммита 1).
Для SQLite включаем foreign keys: иначе ссылочная целостность не проверяется.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker


def create_db_engine(db_url: str) -> Engine:
    engine = create_engine(db_url, future=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
