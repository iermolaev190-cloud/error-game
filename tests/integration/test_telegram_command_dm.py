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
        pass

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "private", "title": None})()


def send_dm(adapter: TelegramAdapter, user_id: int, text: str) -> str:
    return asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=user_id,
                chat_type="private",
                telegram_user_id=user_id,
                text=text,
            )
        )
    )


def test_dm_slash_commands_cover_actions_queries_and_talk(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9940, seed=40)
    created = world_engine.create_character(
        instance.id,
        player_id="9940",
        name="DM Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    resolver.record_last_group_chat(9940, -9940)
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=resolver,
    )

    assert "location=" in send_dm(adapter, 9940, "/look")
    assert "Смотритель" in send_dm(adapter, 9940, "/npcs")
    help_text = send_dm(adapter, 9940, "/help")
    assert "/inventory" in help_text and "/talk <npc>" in help_text
    assert "character=DM Player" in send_dm(adapter, 9940, "/character")
    assert "inventory" in send_dm(adapter, 9940, "/inventory")
    assert "knowledge" in send_dm(adapter, 9940, "/knowledge")

    taken = send_dm(adapter, 9940, "/take medkit")
    assert "action=TAKE" in taken and "ok=true" in taken
    dropped = send_dm(adapter, 9940, "/drop medkit")
    assert "action=DROP" in dropped and "ok=true" in dropped
    dialogue = send_dm(adapter, 9940, "/talk caretaker")
    assert "action=TALK_TO_NPC" in dialogue and "reply=" in dialogue

    moved = send_dm(adapter, 9940, "/move forest")
    assert "action=MOVE" in moved and "ok=true" in moved
    moved = send_dm(adapter, 9940, "/move old_station")
    assert "action=MOVE" in moved and "ok=true" in moved
    inspected = send_dm(adapter, 9940, "/inspect damaged_radio")
    assert "action=INSPECT" in inspected and "claim=" in inspected
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey(
        "old_station"
    )
