import asyncio
import inspect

from world_error.application.action_result import ActionResult
from world_error.application.ai.intent import Intent, IntentType
from world_error.domain.shared.kernel import CharacterId, DomainError, ErrorCode, LocationKey
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.handlers import build_router
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "group", "title": "Test"})()


class FixedMoveInterpreter:
    def interpret(self, raw_input, context):
        return Intent(IntentType.MOVE, context.character_id, target="forest")


class FixedTalkInterpreter:
    def interpret(self, raw_input, context):
        return Intent(
            IntentType.TALK,
            context.character_id,
            target="npc_secret",
            params={"message": raw_input},
        )


def test_handler_contains_only_transport_to_adapter_logic(
    world_engine, uow_factory
) -> None:
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=FixedMoveInterpreter(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )
    router = build_router(adapter)
    callbacks = [handler.callback for handler in router.message.handlers]

    callbacks_by_name = {callback.__name__: callback for callback in callbacks}
    assert set(callbacks_by_name) == {
        "handle_group_message",
        "handle_private_message",
        "handle_registration_start",
        "handle_registration_confirmation",
        "handle_registration_name",
    }
    for callback_name in ("handle_group_message", "handle_private_message"):
        callback = callbacks_by_name[callback_name]
        source = inspect.getsource(callback)
        assert "adapter.handle_message" in source
        assert "handle_intent" not in source
        assert "move_character" not in source
        assert "create_instance" not in source
    for callback_name in (
        "handle_registration_start",
        "handle_registration_confirmation",
        "handle_registration_name",
    ):
        source = inspect.getsource(callbacks_by_name[callback_name])
        assert "registration_handler" in source
        assert "handle_intent" not in source
        assert "create_instance" not in source


def test_foreign_character_is_not_selected_for_telegram_user(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9301, seed=93)
    created = world_engine.create_character(
        instance.id,
        player_id="telegram-user-1",
        name="Owned Character",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    before = world_engine.get_instance(instance.id).state
    events_before = tuple(world_engine.get_events(instance.id))
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=FixedMoveInterpreter(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9301,
                chat_type="group",
                telegram_user_id=2,
                text="move to forest",
            )
        )
    )

    assert response == "Зарегистрируйся в личке: напиши боту /start."
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey(
        "base"
    )
    assert world_engine.get_instance(instance.id).state == before
    assert tuple(world_engine.get_events(instance.id)) == events_before


def test_group_chat_id_is_distinct_from_world_instance_id(
    world_engine, uow_factory
) -> None:
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    chat_id = -9302

    instance_id = resolver.resolve(
        chat_id,
        chat_type="group",
        create_if_missing=True,
    )

    assert instance_id is not None
    assert str(instance_id) != str(chat_id)
    with uow_factory() as uow:
        binding = uow.chat_bindings.get_by_telegram_chat_id(chat_id)
    assert binding is not None
    assert binding.world_instance_id == instance_id


def test_adapter_calls_handle_intent_instead_of_mutating_world_directly(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9303, seed=94)
    created = world_engine.create_character(
        instance.id,
        player_id="3",
        name="Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    original_handle = world_engine.handle_intent
    calls = []

    def reject_intent(world_instance_id, actor_id, intent):
        calls.append((world_instance_id, actor_id, intent))
        return ActionResult.failure(
            "HANDLE_INTENT",
            DomainError(ErrorCode.INVALID_ACTION, "blocked by test"),
        )

    world_engine.handle_intent = reject_intent
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=FixedMoveInterpreter(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )
    try:
        response = asyncio.run(
            adapter.handle_message(
                TelegramIncomingMessage(
                    chat_id=-9303,
                    chat_type="group",
                    telegram_user_id=3,
                    text="move to forest",
                )
            )
        )
    finally:
        world_engine.handle_intent = original_handle

    assert len(calls) == 1
    assert "blocked by test" in response
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey(
        "base"
    )


def test_group_chat_does_not_dispatch_private_npc_dialogue(world_engine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9304, seed=95)
    created = world_engine.create_character(
        instance.id,
        player_id="4",
        name="Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    before = world_engine.get_instance(instance.id).state
    events_before = tuple(world_engine.get_events(instance.id))
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=FixedTalkInterpreter(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9304,
                chat_type="group",
                telegram_user_id=4,
                text="tell me your secret",
            )
        )
    )

    assert "Диалог с NPC — только в DM" in response
    assert "/talk <npc>" in response
    assert world_engine.get_instance(instance.id).state == before
    assert tuple(world_engine.get_events(instance.id)) == events_before
