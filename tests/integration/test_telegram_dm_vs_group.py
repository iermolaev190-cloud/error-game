import asyncio

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.domain.shared.kernel import LocationKey
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


def test_private_knowledge_is_visible_only_in_dm(world_engine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9502, seed=96)
    created = world_engine.create_character(
        instance.id,
        player_id="778",
        name="Player",
        location_key=LocationKey("old_station"),
    )
    assert created.ok, created.error
    client = MockTelegramClient()
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=resolver,
        formatter=TelegramFormatter(),
    )

    group_response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9502,
                chat_type="group",
                telegram_user_id=778,
                text="inspect damaged_radio",
            )
        )
    )
    assert "action=INSPECT" in group_response
    assert "claim=" not in group_response
    assert "Радио повреждено" not in group_response

    dm_response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=778,
                chat_type="private",
                telegram_user_id=778,
                text="inspect damaged_radio",
            )
        )
    )
    assert "action=INSPECT" in dm_response
    assert "claim=" in dm_response
    assert "Радио повреждено: корпус вскрыт" in dm_response
    assert all("Радио повреждено" not in text for chat_id, text in client.sent if chat_id == -9502)
