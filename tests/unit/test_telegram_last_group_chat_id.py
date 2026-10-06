import asyncio

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    async def send_message(self, chat_id: int, text: str) -> None:
        return None

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "group", "title": "Test"})()


def test_group_updates_last_group_each_time_but_dm_does_not(
    world_engine, uow_factory
) -> None:
    first = world_engine.create_instance(telegram_chat_id=-9601, seed=96)
    second = world_engine.create_instance(telegram_chat_id=-9602, seed=97)
    first_character = world_engine.create_character(
        first.id, player_id="961", name="First", location_key=LocationKey("base")
    )
    second_character = world_engine.create_character(
        second.id, player_id="961", name="Second", location_key=LocationKey("base")
    )
    assert first_character.ok and second_character.ok
    first_id = CharacterId(first_character.payload["character_id"])
    second_id = CharacterId(second_character.payload["character_id"])
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=resolver,
    )

    for chat_id in (-9601, -9602):
        asyncio.run(
            adapter.handle_message(
                TelegramIncomingMessage(
                    chat_id=chat_id,
                    chat_type="group",
                    telegram_user_id=961,
                    text="move to forest",
                )
            )
        )
    with uow_factory() as uow:
        state = uow.player_telegram_state.get(961)
    assert state is not None
    assert state.last_group_chat_id == -9602

    asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=961,
                chat_type="private",
                telegram_user_id=961,
                text="move to old_station",
            )
        )
    )
    assert world_engine.get_character(first.id, first_id).location_key == LocationKey(
        "forest"
    )
    assert world_engine.get_character(second.id, second_id).location_key == LocationKey(
        "old_station"
    )
    with uow_factory() as uow:
        state_after_dm = uow.player_telegram_state.get(961)
    assert state_after_dm is not None
    assert state_after_dm.last_group_chat_id == -9602
