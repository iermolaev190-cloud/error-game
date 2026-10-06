import asyncio

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.domain.shared.kernel import CharacterId, LocationKey
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
        return type("Chat", (), {"id": chat_id, "type": "private", "title": None})()


def send_group(adapter: TelegramAdapter, text: str) -> str:
    return asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9920,
                chat_type="group",
                telegram_user_id=9920,
                text=text,
            )
        )
    )


def test_group_slash_commands_route_public_queries_and_actions(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9920, seed=20)
    created = world_engine.create_character(
        instance.id,
        player_id="9920",
        name="Group Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    look = send_group(adapter, "/look")
    assert "location=" in look
    assert "npcs=" in look
    assert "items=" in look
    assert "exits=" in look
    assert "knowledge" not in look
    assert "inventory" not in look

    npcs = send_group(adapter, "/npcs")
    assert "Смотритель" in npcs

    moved = send_group(adapter, "/move forest")
    assert "action=MOVE" in moved
    assert world_engine.get_character(
        instance.id, CharacterId(created.payload["character_id"])
    ).location_key == LocationKey("forest")

    taken = send_group(adapter, "/take medkit")
    assert "action=TAKE" in taken
    assert "ok=true" in taken
    assert client.sent[-1] == (-9920, taken)

    assert "action=MOVE" in send_group(adapter, "/move old_station")
    inspected = send_group(adapter, "/inspect damaged_radio")
    assert "Ссылка: https://example.com/archive-17" in inspected

    assert "action=MOVE" in send_group(adapter, "/move old_station")
    inspected = send_group(adapter, "/inspect damaged_radio")
    assert "Ссылка: https://example.com/archive-17" in inspected
