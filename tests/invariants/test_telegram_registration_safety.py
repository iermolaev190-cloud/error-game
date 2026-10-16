import asyncio

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def get_chat(self, chat_id: int):
        return type("ChatInfo", (), {"id": chat_id, "type": "group", "title": None})()


def make_adapter(world_engine, uow_factory, client):
    return TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )


def test_group_start_never_registers_character(world_engine, uow_factory) -> None:
    client = MockTelegramClient()
    adapter = make_adapter(world_engine, uow_factory, client)

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9960,
                chat_type="group",
                telegram_user_id=9960,
                text="/start",
            )
        )
    )

    assert response == "Регистрация доступна только в личке. Напиши боту лично: /start."
    instances = world_engine.list_instances()
    assert len(instances) == 1
    assert world_engine.find_active_character_for_player(
        instances[0].id, "9960"
    ) is None
    assert client.sent == [(-9960, response)]


def test_group_without_character_prompts_private_registration(
    world_engine, uow_factory
) -> None:
    client = MockTelegramClient()
    adapter = make_adapter(world_engine, uow_factory, client)

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9961,
                chat_type="group",
                telegram_user_id=9961,
                text="hello",
            )
        )
    )

    assert response == "Зарегистрируйся в личке: напиши боту /start."
    instance = world_engine.list_instances()[0]
    assert world_engine.find_active_character_for_player(
        instance.id, "9961"
    ) is None


def test_dm_without_instance_or_character_requires_start(
    world_engine, uow_factory
) -> None:
    client = MockTelegramClient()
    adapter = make_adapter(world_engine, uow_factory, client)

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=9962,
                chat_type="private",
                telegram_user_id=9962,
                text="/look",
            )
        )
    )

    assert response == "Сначала /start."
    assert world_engine.list_instances() == ()
    assert client.sent == [(9962, response)]


def test_dm_without_character_in_active_instance_requires_start(
    world_engine, uow_factory
) -> None:
    client = MockTelegramClient()
    instance = world_engine.create_instance(telegram_chat_id=-9963, seed=63)
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    resolver.record_last_group_chat(9963, -9963)
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=resolver,
    )

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=9963,
                chat_type="private",
                telegram_user_id=9963,
                text="/look",
            )
        )
    )

    assert response == "Сначала /start."
    assert world_engine.find_active_character_for_player(instance.id, "9963") is None
    assert client.sent == [(9963, response)]
