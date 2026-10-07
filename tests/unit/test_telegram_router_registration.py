from types import SimpleNamespace

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.interfaces.telegram.adapter import TelegramAdapter
from world_error.interfaces.telegram.handlers import build_router
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    async def send_message(self, chat_id: int, text: str) -> None:
        pass

    async def get_chat(self, chat_id: int):
        return type("ChatInfo", (), {"id": chat_id, "type": "group", "title": None})()


def test_router_registers_group_private_and_registration_callbacks(
    world_engine, uow_factory
) -> None:
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )
    handlers = build_router(adapter).message.handlers

    by_name = {handler.callback.__name__: handler for handler in handlers}
    assert set(by_name) == {
        "handle_group_message",
        "handle_private_message",
        "handle_registration_start",
        "handle_registration_confirmation",
        "handle_registration_name",
    }

    group_filter = by_name["handle_group_message"].filters[0].magic
    private_filter = by_name["handle_private_message"].filters[0].magic
    for chat_type in ("group", "supergroup"):
        value = SimpleNamespace(chat=SimpleNamespace(type=chat_type))
        assert group_filter.resolve(value) is True
        assert private_filter.resolve(value) is False

    private_value = SimpleNamespace(chat=SimpleNamespace(type="private"))
    assert group_filter.resolve(private_value) is False
    assert private_filter.resolve(private_value) is True
