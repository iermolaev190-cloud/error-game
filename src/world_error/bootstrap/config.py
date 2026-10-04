"""Локальная конфигурация (см. .env.example).

pydantic используется только здесь и в интерфейсах, никогда в domain.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from world_error.domain.world.instance import InstanceEnvironment


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WORLD_ERROR_",
        extra="ignore",
    )

    env: InstanceEnvironment = InstanceEnvironment.DEV
    db_url: str = "sqlite+pysqlite:///./world_error.db"
    content_dir: Path = Path("content")
