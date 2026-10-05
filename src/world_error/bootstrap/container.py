"""Сборка зависимостей приложения."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.application.ai.interpreter import FallbackIntentInterpreter, IntentInterpreter
from world_error.application.ai.providers.mock import MockIntentProvider
from world_error.application.ai.providers.stub import StubIntentProvider
from world_error.application.services.world_engine import WorldEngine
from world_error.bootstrap.config import Settings
from world_error.domain.content.catalog import ContentCatalog
from world_error.infrastructure.content.loader import load_content_catalog
from world_error.infrastructure.db.engine import create_db_engine, create_session_factory
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker
    catalog: ContentCatalog
    uow_factory: Callable[[], SqlAlchemyUnitOfWork]
    world_engine: WorldEngine
    intent_interpreter: IntentInterpreter

    @classmethod
    def build(cls, settings: Settings | None = None) -> "Container":
        settings = settings or Settings()
        catalog = load_content_catalog(Path(settings.content_dir))
        engine = create_db_engine(settings.db_url)
        session_factory = create_session_factory(engine)

        def uow_factory() -> SqlAlchemyUnitOfWork:
            return SqlAlchemyUnitOfWork(session_factory)

        provider = (
            MockIntentProvider()
            if settings.ai_provider == "mock"
            else StubIntentProvider()
        )
        intent_interpreter = FallbackIntentInterpreter(
            provider=provider,
            fallback=CommandIntentParser(),
        )

        return cls(
            settings=settings,
            engine=engine,
            session_factory=session_factory,
            catalog=catalog,
            uow_factory=uow_factory,
            world_engine=WorldEngine(uow_factory=uow_factory, catalog=catalog),
            intent_interpreter=intent_interpreter,
        )

    def dispose(self) -> None:
        self.engine.dispose()
