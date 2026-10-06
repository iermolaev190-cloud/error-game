import asyncio
from unittest.mock import patch

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


def make_adapter(world_engine, uow_factory):
    client = MockTelegramClient()
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=resolver,
    )
    return client, resolver, adapter


def send_dm(adapter, user_id: int, text: str) -> str:
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


def test_dm_without_active_instance_never_creates_instance(
    world_engine, uow_factory
) -> None:
    client, _, adapter = make_adapter(world_engine, uow_factory)

    response = send_dm(adapter, 9701, "move to forest")

    assert "Add the bot to a group" in response
    assert client.sent == [(9701, response)]
    with uow_factory() as uow:
        assert uow.chat_bindings.get_by_telegram_chat_id(9701) is None
        assert uow.player_telegram_state.get(9701) is None


def test_dm_actions_dispatch_through_handle_intent(world_engine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9702, seed=97)
    created = world_engine.create_character(
        instance.id,
        player_id="9702",
        name="Owner",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    _, resolver, adapter = make_adapter(world_engine, uow_factory)
    resolver.record_last_group_chat(9702, -9702)
    original = world_engine.handle_intent

    with patch.object(world_engine, "handle_intent", wraps=original) as dispatch:
        response = send_dm(adapter, 9702, "move to forest")

    assert "action=MOVE" in response
    dispatch.assert_called_once()
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey(
        "forest"
    )


def test_dm_refuses_character_owned_by_another_telegram_user(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9703, seed=98)
    created = world_engine.create_character(
        instance.id,
        player_id="9703",
        name="Other user",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    _, resolver, adapter = make_adapter(world_engine, uow_factory)
    resolver.record_last_group_chat(9704, -9703)
    before = tuple(world_engine.get_events(instance.id))

    response = send_dm(adapter, 9704, "move to forest")

    assert "No active character" in response
    assert tuple(world_engine.get_events(instance.id)) == before
    assert world_engine.get_character(
        instance.id, CharacterId(created.payload["character_id"])
    ).location_key == LocationKey("base")


def test_dm_does_not_use_character_from_another_instance(
    world_engine, uow_factory
) -> None:
    selected = world_engine.create_instance(telegram_chat_id=-9705, seed=99)
    other = world_engine.create_instance(telegram_chat_id=-9706, seed=100)
    created = world_engine.create_character(
        other.id,
        player_id="9705",
        name="Other world character",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    _, resolver, adapter = make_adapter(world_engine, uow_factory)
    resolver.record_last_group_chat(9705, -9705)
    before = tuple(world_engine.get_events(other.id))
    selected_before = tuple(world_engine.get_events(selected.id))

    response = send_dm(adapter, 9705, "move to forest")

    assert "No active character" in response
    assert tuple(world_engine.get_events(other.id)) == before
    assert world_engine.get_character(
        other.id, CharacterId(created.payload["character_id"])
    ).location_key == LocationKey("base")
    assert tuple(world_engine.get_events(selected.id)) == selected_before


def test_dm_rejects_foreign_instance_character_even_if_resolver_returns_it(
    world_engine, uow_factory, monkeypatch
) -> None:
    selected = world_engine.create_instance(telegram_chat_id=-9707, seed=101)
    foreign = world_engine.create_instance(telegram_chat_id=-9708, seed=102)
    created = world_engine.create_character(
        foreign.id,
        player_id="9707",
        name="Foreign world character",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    foreign_character = world_engine.get_character(
        foreign.id, CharacterId(created.payload["character_id"])
    )
    client, resolver, adapter = make_adapter(world_engine, uow_factory)
    resolver.record_last_group_chat(9707, -9707)
    monkeypatch.setattr(
        resolver,
        "resolve_dm_character",
        lambda *_args: foreign_character,
    )
    selected_before = tuple(world_engine.get_events(selected.id))
    foreign_before = tuple(world_engine.get_events(foreign.id))

    response = send_dm(adapter, 9707, "move to forest")

    assert "No active character" in response
    assert client.sent == [(9707, response)]
    assert tuple(world_engine.get_events(selected.id)) == selected_before
    assert tuple(world_engine.get_events(foreign.id)) == foreign_before
