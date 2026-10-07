"""Configure and run the aiogram polling transport."""

from __future__ import annotations

from aiogram import Bot, Dispatcher

from world_error.application.ports.telegram import TelegramChat
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.interfaces.telegram.adapter import TelegramAdapter
from world_error.interfaces.telegram.handlers import build_router
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class AiogramTelegramClient:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_message(self, chat_id: int, text: str) -> None:
        await self._bot.send_message(chat_id=chat_id, text=text)

    async def get_chat(self, chat_id: int) -> TelegramChat:
        chat = await self._bot.get_chat(chat_id)
        return TelegramChat(id=chat.id, type=chat.type, title=chat.title)


async def start_polling(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    if not settings.telegram_bot_token.strip():
        raise ValueError("WORLD_ERROR_TELEGRAM_BOT_TOKEN must be configured")

    container = Container.build(settings)
    bot = Bot(token=settings.telegram_bot_token)
    adapter = TelegramAdapter(
        telegram_client=AiogramTelegramClient(bot),
        world_engine=container.world_engine,
        intent_interpreter=container.intent_interpreter,
        instance_resolver=GroupInstanceResolver(
            container.world_engine,
            container.uow_factory,
        ),
        admin_chat_id=settings.admin_chat_id,
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(adapter))
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        container.dispose()
