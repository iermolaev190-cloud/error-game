import asyncio

from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.registry import INTENT_HANDLERS
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
        return type("Chat", (), {"id": chat_id, "type": "group", "title": "Test"})()


class MoveInterpreter:
    def interpret(self, raw_input, context):
        return Intent(
            type=IntentType.MOVE,
            actor_id=context.character_id,
            target="forest",
        )


def test_group_update_runs_intent_and_sends_formatted_result(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9201, seed=92)
    created = world_engine.create_character(
        instance.id,
        player_id="777",
        name="Group Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=MoveInterpreter(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
        formatter=TelegramFormatter(),
    )

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9201,
                chat_type="group",
                telegram_user_id=777,
                text="move to forest",
            )
        )
    )

    assert "action=MOVE" in response
    assert "ok=true" in response
    assert "to=forest" in response
    assert client.sent == [(-9201, response)]
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey(
        "forest"
    )
    assert IntentType.TALK in INTENT_HANDLERS


def test_unknown_group_first_update_creates_binding_then_refuses_missing_character(
    world_engine, uow_factory
) -> None:
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=MoveInterpreter(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=-9202,
                chat_type="supergroup",
                telegram_user_id=778,
                text="hello",
            )
        )
    )

    assert "No active character" in response
    with uow_factory() as uow:
        binding = uow.chat_bindings.get_by_telegram_chat_id(-9202)
    assert binding is not None
    assert str(binding.world_instance_id) != str(-9202)


def test_private_chat_never_creates_instance_or_sends_to_group(
    world_engine, uow_factory
) -> None:
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=MoveInterpreter(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    response = asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=555,
                chat_type="private",
                telegram_user_id=777,
                text="move to forest",
            )
        )
    )

    assert response == "Add the bot to a group before using it in a private chat."
    assert client.sent == [(555, response)]
    with uow_factory() as uow:
        assert uow.chat_bindings.get_by_telegram_chat_id(555) is None
