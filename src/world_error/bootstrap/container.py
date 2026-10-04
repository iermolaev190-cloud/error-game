"""Сборка зависимостей приложения."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.application.services.world_engine import WorldEngine
from world_error.bootstrap.config import Settings
from world_error.infrastructure.db.engine import create_db_engine, create_session_factory
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker
    uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    world_engine: WorldEngine

    @classmethod
    def build(cls, settings: Settings | None = None) -> "Container":
        settings = settings or Settings()
        engine = create_db_engine(settings.db_url)
        session_factory = create_session_factory(engine)

        def uow_factory() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            uow_factory=uow_factory,
            world_engine=WorldEngine(uow_factory=uow_factory),
        )

    def dispose(self) -> None:
        self.engine.dispose()
