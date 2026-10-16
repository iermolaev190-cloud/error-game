import asyncio

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.application.ai.command_router import CommandRouter
from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.key_resolver import InstanceKeyResolver
from world_error.application.ai.routed_command import RoutedCommand
from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.command_executor import TelegramCommandExecutor
from world_error.interfaces.telegram.formatter import TelegramFormatter
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
                chat_id=-9930,
                chat_type="group",
                telegram_user_id=9930,
                text=text,
            )
        )
    )


def test_command_router_does_not_mutate_world(world_engine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9930, seed=30)
    created = world_engine.create_character(
        instance.id,
        player_id="9930",
        name="Router Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    events_before = tuple(world_engine.get_events(instance.id))
    location_before = world_engine.get_character(instance.id, character_id).location_key

    routed = CommandRouter().route("/move@BotUsername forest", actor_id=character_id)

    assert routed.kind == "intent"
    assert tuple(world_engine.get_events(instance.id)) == events_before
    assert world_engine.get_character(instance.id, character_id).location_key == location_before


def test_key_resolution_never_returns_foreign_instance_item(
    world_engine, uow_factory
) -> None:
    selected = world_engine.create_instance(telegram_chat_id=-9931, seed=31)
    foreign = world_engine.create_instance(telegram_chat_id=-9932, seed=32)
    with uow_factory() as uow:
        foreign_id = next(
            item.id
            for item in uow.items.list_at_location(foreign.id, LocationKey("base"))
            if item.key == "medkit"
        )

    resolved = InstanceKeyResolver(uow_factory).resolve_location_item(
        selected.id, LocationKey("base"), "medkit"
    )

    assert resolved is not None
    assert resolved != foreign_id
    with uow_factory() as uow:
        assert uow.items.get(selected.id, resolved).world_instance_id == selected.id


def test_query_commands_bypass_handle_intent_and_public_look_is_safe(
    world_engine, uow_factory, monkeypatch
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9930, seed=33)
    created = world_engine.create_character(
        instance.id,
        player_id="9930",
        name="Router Player",
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
        raise AssertionError("query commands must not go through handle_intent")

    monkeypatch.setattr(world_engine, "handle_intent", forbidden)
    response = send_group(adapter, "/look")

    assert "location=" in response
    assert "npcs=" in response
    assert "items=" in response
    assert "exits=" in response
    assert "inventory" not in response
    assert "knowledge" not in response


def test_action_commands_mutate_only_through_handle_intent(
    world_engine, uow_factory, monkeypatch
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9930, seed=34)
    created = world_engine.create_character(
        instance.id,
        player_id="9930",
        name="Router Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )
    original = world_engine.handle_intent
    calls = []

    def tracked_handle_intent(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)

    monkeypatch.setattr(world_engine, "handle_intent", tracked_handle_intent)
    response = send_group(adapter, "/take medkit")

    assert "action=TAKE" in response and "ok=true" in response
    assert len(calls) == 1


def test_transfer_commands_reject_foreign_and_nonlocal_characters(
    world_engine, uow_factory
) -> None:
    selected = world_engine.create_instance(telegram_chat_id=-9933, seed=35)
    foreign = world_engine.create_instance(telegram_chat_id=-9934, seed=36)
    actor_result = world_engine.create_character(
        selected.id,
        player_id="9933",
        name="Local Actor",
        location_key=LocationKey("base"),
    )
    foreign_result = world_engine.create_character(
        foreign.id,
        player_id="9934",
        name="Foreign Character",
        location_key=LocationKey("base"),
    )
    remote_result = world_engine.create_character(
        selected.id,
        player_id="9935",
        name="Remote Character",
        location_key=LocationKey("forest"),
    )
    assert actor_result.ok and foreign_result.ok and remote_result.ok
    actor_id = CharacterId(actor_result.payload["character_id"])
    actor = world_engine.get_character(selected.id, actor_id)
    executor = TelegramCommandExecutor(
        world_engine=world_engine,
        key_resolver=InstanceKeyResolver(uow_factory),
        formatter=TelegramFormatter(),
    )
    commands = (
        (IntentType.GIVE, {"item_key": "medkit"}),
        (IntentType.SHARE_KNOWLEDGE, {"information_key": "dispatch_log"}),
        (
            IntentType.TRADE,
            {"offered_item_key": "medkit", "requested_item_key": "credits"},
        ),
    )
    before_selected = tuple(world_engine.get_events(selected.id))
    before_foreign = tuple(world_engine.get_events(foreign.id))

    for intent_type, params in commands:
        response = asyncio.run(
            executor.execute(
                RoutedCommand(
                    kind="intent",
                    intent=Intent(
                        type=intent_type,
                        actor_id=actor_id,
                        target=foreign_result.payload["character_id"],
                        params=params,
                    ),
                ),
                world_instance_id=selected.id,
                character=actor,
                private=False,
            )
        )
        assert "ok=false" in response
        assert "Не удалось найти персонажа" in response

    remote_response = asyncio.run(
        executor.execute(
            RoutedCommand(
                kind="intent",
                intent=Intent(
                    type=IntentType.GIVE,
                    actor_id=actor_id,
                    target=remote_result.payload["character_id"],
                    params={"item_key": "medkit"},
                ),
            ),
            world_instance_id=selected.id,
            character=actor,
            private=False,
        )
    )
    assert "ok=false" in remote_response
    assert "Не удалось найти персонажа" in remote_response
    assert tuple(world_engine.get_events(selected.id)) == before_selected
    assert tuple(world_engine.get_events(foreign.id)) == before_foreign
