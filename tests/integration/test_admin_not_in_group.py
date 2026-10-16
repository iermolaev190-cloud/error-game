import asyncio

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
        return type("Chat", (), {"id": chat_id, "type": "group", "title": "Game"})()


def test_admin_command_in_game_group_is_rejected_before_game_routing(
    world_engine, uow_factory
) -> None:
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=object(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
        admin_chat_id=-9915,
    )

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9916,
                chat_type="group",
                telegram_user_id=9916,
                text="/admin worlds",
            )
        )
    )

    assert response == "Команда не найдена."
    assert client.sent == [(-9916, response)]
    assert world_engine.list_instances() == ()
