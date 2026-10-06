import asyncio

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.domain.shared.kernel import LocationKey
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


def send_group(adapter: TelegramAdapter, text: str) -> str:
    return asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9921,
                chat_type="group",
                telegram_user_id=9921,
                text=text,
            )
        )
    )


def test_private_queries_and_talk_are_rejected_before_execution(
    world_engine, uow_factory, monkeypatch
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9921, seed=21)
    created = world_engine.create_character(
        instance.id,
        player_id="9921",
        name="Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("private operation must not be executed in a group")

    monkeypatch.setattr(world_engine, "get_inventory", forbidden)
    monkeypatch.setattr(world_engine, "get_knowledge", forbidden)
    monkeypatch.setattr(world_engine, "get_character", forbidden)
    monkeypatch.setattr(world_engine, "talk_to_npc", forbidden)

    for command in ("/inventory", "/knowledge", "/character", "/talk caretaker"):
        response = send_group(adapter, command)
        assert response == "Используй DM для приватных команд."
