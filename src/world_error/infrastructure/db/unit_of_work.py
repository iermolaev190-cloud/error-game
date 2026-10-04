"""Транзакционная граница.

Состояние мира и событие фиксируются вместе; при исключении ``__exit__``
откатывает транзакцию, поэтому частично применённого изменения не бывает.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from world_error.infrastructure.db.repositories import (
    SqlCharacterRepository,
    SqlEventLogRepository,
    SqlInformationRepository,
    SqlKnowledgeRepository,
    SqlLocationStateRepository,
    SqlNpcRepository,
    SqlWorldInstanceRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self.world_instances: SqlWorldInstanceRepository
        self.events: SqlEventLogRepository
        self.characters: SqlCharacterRepository
        self.locations: SqlLocationStateRepository
        self.information: SqlInformationRepository
        self.knowledge: SqlKnowledgeRepository
        self.npcs: SqlNpcRepository

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self.world_instances = SqlWorldInstanceRepository(self._session)
        self.events = SqlEventLogRepository(self._session)
        self.characters = SqlCharacterRepository(self._session)
        self.locations = SqlLocationStateRepository(self._session)
        self.information = SqlInformationRepository(self._session)
        self.knowledge = SqlKnowledgeRepository(self._session)
        self.npcs = SqlNpcRepository(self._session)
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
