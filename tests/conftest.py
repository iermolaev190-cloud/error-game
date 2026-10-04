"""Общие фикстуры.

Здесь же — запуск CLI/Alembic в отдельных процессах: сценарии обязаны проверять
состояние после смены процесса, а не только новой сессии.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Iterator

import pytest
from sqlalchemy.engine import Engine

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.content.catalog import ContentCatalog
from world_error.infrastructure.content.loader import load_content_catalog
from world_error.infrastructure.db.engine import create_db_engine, create_session_factory
from world_error.infrastructure.db.tables import metadata
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"


@pytest.fixture(scope="session", autouse=True)
def ensure_pytest_tmp_dir() -> None:
    Path(".pytest_tmp").mkdir(exist_ok=True)


def sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"


def run_python(args: list[str], *, db_url: str) -> subprocess.CompletedProcess[str]:
    """Запустить отдельный процесс Python (новый интерпретатор).

    UTF-8 выставляется явно: контент и подписи в проекте на русском, и вывод
    дочернего процесса не должен зависеть от кодовой страницы консоли.
    """
    env = {
        **os.environ,
        "WORLD_ERROR_DB_URL": db_url,
        "PYTHONPATH": str(SRC_DIR),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.fixture()
def db_url(tmp_path: Path) -> str:
    return sqlite_url(tmp_path / "test.db")


@pytest.fixture()
def engine(db_url: str) -> Iterator[Engine]:
    db_engine = create_db_engine(db_url)
    metadata.create_all(db_engine)
    yield db_engine
    db_engine.dispose()


@pytest.fixture()
def uow_factory(engine: Engine) -> Callable[[], SqlAlchemyUnitOfWork]:
    session_factory = create_session_factory(engine)
    return lambda: SqlAlchemyUnitOfWork(session_factory)


@pytest.fixture()
def content_dir() -> Path:
    return REPO_ROOT / "content"


@pytest.fixture()
def catalog(content_dir: Path) -> ContentCatalog:
    return load_content_catalog(content_dir)


@pytest.fixture()
def world_engine(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork], catalog: ContentCatalog
) -> WorldEngine:
    return WorldEngine(uow_factory=uow_factory, catalog=catalog)


@pytest.fixture()
def cli() -> Callable[..., subprocess.CompletedProcess[str]]:
    """Запуск CLI: ``cli(db_url, "create-world", ...)`` — отдельный процесс."""

    def _run(db_url: str, *args: str) -> subprocess.CompletedProcess[str]:
        return run_python(["-m", "world_error", *args], db_url=db_url)

    return _run


@pytest.fixture()
def alembic_upgrade() -> Callable[[str], subprocess.CompletedProcess[str]]:
    """``alembic upgrade head`` на чистой БД — отдельный процесс."""

    def _run(db_url: str) -> subprocess.CompletedProcess[str]:
        return run_python(["-m", "alembic", "upgrade", "head"], db_url=db_url)

    return _run
