import asyncio

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.formatter import TelegramFormatter
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "private", "title": None})()


def make_dm_adapter(world_engine, uow_factory):
    client = MockTelegramClient()
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=resolver,
        formatter=TelegramFormatter(),
    )
    return client, resolver, adapter


def send_dm(adapter, text: str) -> str:
    return asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=777,
                chat_type="private",
                telegram_user_id=777,
                text=text,
            )
        )
    )


def test_dm_move_inspect_talk_inventory_and_knowledge(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9501, seed=95)
    created = world_engine.create_character(
        instance.id,
        player_id="777",
        name="DM Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    with uow_factory() as uow:
        medkit = next(
            item
            for item in uow.items.list_at_location(instance.id, LocationKey("base"))
            if item.key == "medkit"
        )
    taken = world_engine.take_item(
        instance.id, character_id=character_id, item_id=medkit.id
    )
    assert taken.ok, taken.error
    client, resolver, adapter = make_dm_adapter(world_engine, uow_factory)
    resolver.record_last_group_chat(777, -9501)

    assert "location=" in send_dm(adapter, "/look")
    assert "npcs=" in send_dm(adapter, "/npcs")
    assert "commands:" in send_dm(adapter, "/help")
    assert "character=DM Player" in send_dm(adapter, "/character")

    dropped = send_dm(adapter, "/drop medkit")
    assert "action=DROP" in dropped
    assert "ok=true" in dropped
    taken = send_dm(adapter, "/take medkit")
    assert "action=TAKE" in taken
    assert "ok=true" in taken

    moved = send_dm(adapter, "/move forest")
    assert "action=MOVE" in moved
    moved = send_dm(adapter, "move to old_station")
    assert "action=MOVE" in moved

    inspected = send_dm(adapter, "inspect damaged_radio")
    assert "action=INSPECT" in inspected
    assert "claim=" in inspected

    knowledge = send_dm(adapter, "/knowledge")
    assert "knowledge" in knowledge
    assert "claim=" in knowledge

    inventory = send_dm(adapter, "/inventory")
    assert "inventory" in inventory
    assert "item: name=" in inventory

    dialogue = send_dm(adapter, "/talk mechanic")
    assert "action=TALK_TO_NPC" in dialogue
    assert "reply=" in dialogue

    moved = send_dm(adapter, "move to forest")
    assert "action=MOVE" in moved
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey(
        "forest"
    )
    assert all(chat_id == 777 for chat_id, _ in client.sent)
