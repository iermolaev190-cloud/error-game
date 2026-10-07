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
        return type("Chat", (), {"id": chat_id, "type": "private", "title": None})()


def test_admin_command_in_dm_is_rejected_before_dm_resolution(
    world_engine, uow_factory
) -> None:
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=object(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
        admin_chat_id=-9917,
    )

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=9918,
                chat_type="private",
                telegram_user_id=9918,
                text="/admin worlds",
            )
        )
    )

    assert response == "Admin-команды доступны только в admin-чате."
    assert client.sent == [(9918, response)]
    assert world_engine.list_instances() == ()
