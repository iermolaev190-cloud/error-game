import asyncio
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.types import Chat, Message, Update, User

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.domain.characters.character import CharacterLifecycle
from world_error.domain.events.event import EventType
from world_error.interfaces.telegram.adapter import TelegramAdapter
from world_error.interfaces.telegram.handlers import build_router
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    async def send_message(self, chat_id: int, text: str) -> None:
        pass

    async def get_chat(self, chat_id: int):
        return type("ChatInfo", (), {"id": chat_id, "type": "private", "title": None})()


def build_message(update_id: int, user_id: int, text: str) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=user_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="Player"),
            text=text,
        ),
    )


def test_start_registration_cancel_then_create_and_repeated_start(
    world_engine, uow_factory, monkeypatch
) -> None:
    async def run() -> None:
        telegram_user_id = 9950
        instance = world_engine.create_instance(telegram_chat_id=-9950, seed=50)
        resolver = GroupInstanceResolver(world_engine, uow_factory)
        resolver.record_last_group_chat(telegram_user_id, -9950)
        adapter = TelegramAdapter(
            telegram_client=MockTelegramClient(),
            world_engine=world_engine,
            intent_interpreter=CommandIntentParser(),
            instance_resolver=resolver,
        )
        dispatcher = Dispatcher()
        dispatcher.include_router(build_router(adapter))
        bot = Bot(token="123456:TEST_TOKEN_FOR_REGISTRATION_TEST")
        sent: list[tuple[int, str]] = []

        async def capture_answer(self: Message, text: str, **kwargs) -> Message:
            sent.append((self.chat.id, text))
            return self

        monkeypatch.setattr(Message, "answer", capture_answer)
        try:
            await dispatcher.feed_update(
                bot, build_message(1, telegram_user_id, "/start")
            )
            await dispatcher.feed_update(
                bot, build_message(2, telegram_user_id, "Отмена")
            )
            await dispatcher.feed_update(
                bot, build_message(3, telegram_user_id, "/start")
            )
            await dispatcher.feed_update(
                bot, build_message(4, telegram_user_id, "Да")
            )
            await dispatcher.feed_update(
                bot, build_message(5, telegram_user_id, "Ada")
            )
            await dispatcher.feed_update(
                bot, build_message(6, telegram_user_id, "/start")
            )
        finally:
            await bot.session.close()

        characters = world_engine.find_active_character_for_player(
            instance.id, str(telegram_user_id)
        )
        events = world_engine.get_events(instance.id)
        assert characters is not None
        assert characters.name == "Ada"
        assert characters.lifecycle is CharacterLifecycle.ALIVE
        assert sum(event.type is EventType.CHARACTER_CREATED for event in events) == 1
        assert [text for _, text in sent] == [
            "У тебя нет character. Создать? Ответь «Да» или «Отмена».",
            "Ок. Напиши /start позже.",
            "У тебя нет character. Создать? Ответь «Да» или «Отмена».",
            "Как тебя зовут?",
            "Привет, Ada! Локация: base. /help.",
            "Привет, Ada! Локация: base. /help.",
        ]

    asyncio.run(run())


def test_start_without_any_instance_refuses_registration(
    world_engine, uow_factory, monkeypatch
) -> None:
    async def run() -> None:
        telegram_user_id = 9951
        adapter = TelegramAdapter(
            telegram_client=MockTelegramClient(),
            world_engine=world_engine,
            intent_interpreter=CommandIntentParser(),
            instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
        )
        dispatcher = Dispatcher()
        dispatcher.include_router(build_router(adapter))
        bot = Bot(token="123456:TEST_TOKEN_FOR_REGISTRATION_TEST")
        sent: list[str] = []

        async def capture_answer(self: Message, text: str, **kwargs) -> Message:
            sent.append(text)
            return self

        monkeypatch.setattr(Message, "answer", capture_answer)
        try:
            await dispatcher.feed_update(
                bot, build_message(1, telegram_user_id, "/start")
            )
        finally:
            await bot.session.close()

        assert sent == [
            "Сначала добавь бота в игровую группу, затем напиши /start в личке."
        ]
        assert world_engine.list_instances() == ()

    asyncio.run(run())
