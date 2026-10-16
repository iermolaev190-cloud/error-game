import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.domain.shared.kernel import LocationKey
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.handlers import build_router
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def get_chat(self, chat_id: int):
        return type("ChatInfo", (), {"id": chat_id, "type": "private", "title": None})()


def test_private_update_reaches_adapter_and_dm_handler(
    world_engine, uow_factory
) -> None:
    async def run() -> None:
        instance = world_engine.create_instance(telegram_chat_id=-9941, seed=41)
        created = world_engine.create_character(
            instance.id,
            player_id="9941",
            name="DM Router Player",
            location_key=LocationKey("base"),
        )
        assert created.ok, created.error

        telegram_client = MockTelegramClient()
        resolver = GroupInstanceResolver(world_engine, uow_factory)
        resolver.record_last_group_chat(9941, -9941)
        adapter = TelegramAdapter(
            telegram_client=telegram_client,
            world_engine=world_engine,
            intent_interpreter=CommandIntentParser(),
            instance_resolver=resolver,
        )
        adapter_call = AsyncMock(wraps=adapter.handle_message)
        adapter.handle_message = adapter_call
        dm_handler_call = AsyncMock(wraps=adapter._dm_handler.handle_message)
        adapter._dm_handler.handle_message = dm_handler_call

        dispatcher = Dispatcher()
        dispatcher.include_router(build_router(adapter))
        bot = Bot(token="123456:TEST_TOKEN_FOR_ROUTER_TEST")
        update = Update(
            update_id=1,
            message=Message(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=Chat(id=9941, type="private"),
                from_user=User(id=9941, is_bot=False, first_name="Player"),
                text="/look",
            ),
        )
        try:
            await dispatcher.feed_update(bot, update)
        finally:
            await bot.session.close()

        adapter_call.assert_awaited_once_with(
            TelegramIncomingMessage(
                chat_id=9941,
                chat_type="private",
                telegram_user_id=9941,
                text="/look",
            )
        )
        dm_handler_call.assert_awaited_once_with(
            chat_id=9941,
            telegram_user_id=9941,
            text="/look",
        )
        assert telegram_client.sent
        assert telegram_client.sent[0][0] == 9941
        assert "location=" in telegram_client.sent[0][1]

    asyncio.run(run())
