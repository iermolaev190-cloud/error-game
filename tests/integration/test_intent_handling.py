from types import SimpleNamespace
from typing import Callable

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.interpreter import IntentContext
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.items.item import ItemOwnerType
from world_error.domain.shared.kernel import (
    CharacterId,
    ErrorCode,
    ItemId,
    LocationKey,
)
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


def create_character(world_engine: WorldEngine, instance_id, player_id: str) -> CharacterId:
    created = world_engine.create_character(instance_id, player_id=player_id, name=player_id)
    assert created.ok, created.error
    return CharacterId(created.payload["character_id"])


def test_move_intent_matches_direct_world_engine_call(world_engine: WorldEngine) -> None:
    instance_intent = world_engine.create_instance(telegram_chat_id=-2001, seed=1)
    instance_direct = world_engine.create_instance(telegram_chat_id=-2002, seed=1)
    actor_intent = create_character(world_engine, instance_intent.id, "player-intent")
    actor_direct = create_character(world_engine, instance_direct.id, "player-direct")
    context = IntentContext(
        player_id="player-intent",
        character_id=actor_intent,
        location_id="base",
        visible_objects=(),
        allowed_actions=("MOVE",),
    )
    intent = CommandIntentParser().interpret("move to forest", context)
    assert intent is not None

    routed = world_engine.handle_intent(instance_intent.id, actor_intent, intent)
    direct = world_engine.move_character(
        instance_direct.id,
        character_id=actor_direct,
        to_location_key=LocationKey("forest"),
    )

    assert routed.ok == direct.ok is True
    assert routed.action == direct.action == "MOVE"
    assert routed.payload["from"] == direct.payload["from"] == "base"
    assert routed.payload["to"] == direct.payload["to"] == "forest"
    assert world_engine.get_character(instance_intent.id, actor_intent).location_key == LocationKey("forest")
    assert world_engine.get_character(instance_direct.id, actor_direct).location_key == LocationKey("forest")


def test_intents_use_real_world_information_and_items(
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-2001, seed=42)
    actor = create_character(world_engine, instance.id, "alice")
    receiver = create_character(world_engine, instance.id, "bob")

    for destination in ("forest", "old_station"):
        moved = world_engine.handle_intent(
            instance.id,
            actor,
            Intent(IntentType.MOVE, actor, target=destination),
        )
        assert moved.ok, moved.error
    inspect = world_engine.handle_intent(
        instance.id,
        actor,
        Intent(IntentType.INSPECT, actor, target="damaged_radio"),
    )
    assert inspect.ok, inspect.error
    assert world_engine.get_knowledge(instance.id, actor)

    for destination in ("forest", "base"):
        moved = world_engine.handle_intent(
            instance.id,
            actor,
            Intent(IntentType.MOVE, actor, target=destination),
        )
        assert moved.ok, moved.error
    with uow_factory() as uow:
        inventory_at_base = uow.items.list_at_location(instance.id, LocationKey("base"))
        medkit = next(item for item in inventory_at_base if item.key == "medkit")
        credits = next(item for item in inventory_at_base if item.key == "credits")
        assert medkit.owner_type is ItemOwnerType.LOCATION
        assert credits.owner_type is ItemOwnerType.LOCATION

    take_medkit = world_engine.handle_intent(
        instance.id,
        actor,
        Intent(IntentType.TAKE, actor, target=str(medkit.id)),
    )
    take_credits = world_engine.handle_intent(
        instance.id,
        actor,
        Intent(IntentType.TAKE, actor, target=str(credits.id), params={"quantity": 1}),
    )
    assert take_medkit.ok, take_medkit.error
    assert take_credits.ok, take_credits.error

    given = world_engine.handle_intent(
        instance.id,
        actor,
        Intent(
            IntentType.GIVE,
            actor,
            target=str(receiver),
            params={"item_id": ItemId(str(medkit.id))},
        ),
    )
    assert given.ok, given.error
    assert {
        item.key for item in world_engine.get_inventory(instance.id, receiver).items
    } == {"medkit"}


def test_unknown_or_system_intent_returns_failure_without_state_change(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-2001, seed=42)
    actor = create_character(world_engine, instance.id, "alice")
    state_before = world_engine.get_instance(instance.id).state
    events_before = tuple(world_engine.get_events(instance.id))

    result = world_engine.handle_intent(
        instance.id,
        actor,
        SimpleNamespace(type="PUMP_CONSEQUENCES", actor_id=actor, target=None, params={}),
    )

    assert not result.ok
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ACTION
    assert world_engine.get_instance(instance.id).state == state_before
    assert tuple(world_engine.get_events(instance.id)) == events_before
