import asyncio

import pytest

from world_error.bootstrap.config import Settings
from world_error.interfaces.telegram.bot import start_polling


def test_start_polling_requires_configured_bot_token() -> None:
    with pytest.raises(
        ValueError,
        match="WORLD_ERROR_TELEGRAM_BOT_TOKEN must be configured",
    ):
        asyncio.run(start_polling(Settings(telegram_bot_token="")))


def test_settings_reads_telegram_token_from_prefixed_environment(monkeypatch) -> None:
    monkeypatch.setenv("WORLD_ERROR_TELEGRAM_BOT_TOKEN", "test-token")

    assert Settings(_env_file=None).telegram_bot_token == "test-token"
