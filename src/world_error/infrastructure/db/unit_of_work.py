"""Транзакционная граница.

Состояние мира и событие фиксируются вместе; при исключении ``__exit__``
откатывает транзакцию, поэтому частично применённого изменения не бывает.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from world_error.infrastructure.db.repositories import (
    SqlEventLogRepository,
    SqlWorldInstanceRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self.world_instances: SqlWorldInstanceRepository
        self.events: SqlEventLogRepository

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self.world_instances = SqlWorldInstanceRepository(self._session)
        self.events = SqlEventLogRepository(self._session)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        assert self._session is not None
        try:
            if exc_type is not None:
                self._session.rollback()
        finally:
            self._session.close()

    def commit(self) -> None:
        assert self._session is not None
        self._session.commit()

    def rollback(self) -> None:
        assert self._session is not None
        self._session.rollback()
