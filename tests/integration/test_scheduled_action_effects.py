"""Scheduled CHARACTER_ARRIVAL validates the world again at firing time."""

from __future__ import annotations

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import CharacterLifecycle
from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import CharacterId, EventId, LocationKey, ScheduledEventId
from world_error.domain.time.scheduled_event import ScheduledEventStatus, ScheduledTriggerKind
from world_error.domain.time.action_cost import CostTicks
from world_error.domain.world.instance import WorldInstance


def make_world(world_engine: WorldEngine) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=-1001, seed=42)


def schedule_arrival(
    world_engine: WorldEngine,
    instance: WorldInstance,
    character_id: CharacterId,
    to_location_key: str,
) -> ScheduledEventId:
    cause = world_engine.get_events(instance.id)[-1].id
    result = world_engine.schedule_event(
        instance.id,
        cause_event_id=cause,
        event_key="CHARACTER_ARRIVAL",
        idempotency_key=f"arrival-{character_id}-{to_location_key}",
        trigger_kind=ScheduledTriggerKind.AT_TICK,
        due_tick=world_engine.get_instance(instance.id).state.world_tick + 3,
        payload={"character_id": str(character_id), "to_location_key": to_location_key},
    )
    assert result.ok is True, result.error
    return ScheduledEventId(result.payload["scheduled_event_id"])


def test_character_arrival_applies_only_after_due_and_validates_graph(
    world_engine: WorldEngine,
) -> None:
    instance = make_world(world_engine)
    created = world_engine.create_character(instance.id, player_id="player-a", name="Аня")
    character_id = CharacterId(created.payload["character_id"])
    scheduled_id = schedule_arrival(world_engine, instance, character_id, "forest")
    world_engine.advance_tick(instance.id)
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey("base")
    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.PENDING
    )

    world_engine.advance_tick(instance.id)

    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey("forest")
    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.APPLIED
    )
    event_types = [event.type for event in world_engine.get_events(instance.id)]
    assert EventType.SCHEDULED_EVENT_TRIGGERED in event_types
    assert EventType.CHARACTER_MOVED in event_types


def test_travel_action_creates_costed_scheduled_arrival(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    created = world_engine.create_character(instance.id, player_id="traveler", name="Путник")
    character_id = CharacterId(created.payload["character_id"])
    start_tick = world_engine.get_instance(instance.id).state.world_tick

    travel = world_engine.begin_travel(
        instance.id,
        character_id=character_id,
        to_location_key=LocationKey("forest"),
        cost_ticks=CostTicks(3),
        idempotency_key="traveler-base-forest",
    )

    assert travel.ok is True, travel.error
    assert world_engine.get_instance(instance.id).state.world_tick == start_tick + 3
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey("base")
    scheduled_id = ScheduledEventId(travel.payload["scheduled_event_id"])
    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.PENDING
    )
    cost_events = [
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.ACTION_COST_TICK_CONSUMED
    ]
    assert len(cost_events) == 1
    assert dict(cost_events[0].payload) == {
        "action": "BEGIN_TRAVEL",
        "cost": 3,
        "from_tick": start_tick,
        "to_tick": start_tick + 3,
    }

    world_engine.advance_tick(instance.id)

    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.APPLIED
    )
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey("forest")


def test_invalid_character_arrival_fails_without_bypassing_graph(
    world_engine: WorldEngine,
) -> None:
    instance = make_world(world_engine)
    created = world_engine.create_character(instance.id, player_id="player-a", name="Аня")
    character_id = CharacterId(created.payload["character_id"])
    scheduled_id = schedule_arrival(world_engine, instance, character_id, "old_station")

    world_engine.advance_tick(instance.id)
    world_engine.advance_tick(instance.id)

    scheduled = world_engine.get_scheduled_event(instance.id, scheduled_id)
    assert scheduled.status is ScheduledEventStatus.FAILED
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey("base")
    failed = [
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.SCHEDULED_EVENT_FAILED
    ]
    assert len(failed) == 1
    assert failed[0].payload["error_code"] == "INVALID_ACTION"


def test_dead_character_arrival_fails_after_schedule(
    world_engine: WorldEngine,
) -> None:
    instance = make_world(world_engine)
    created = world_engine.create_character(instance.id, player_id="player-a", name="Аня")
    character_id = CharacterId(created.payload["character_id"])
    scheduled_id = schedule_arrival(world_engine, instance, character_id, "forest")
    cause_event_id = world_engine.get_events(instance.id)[-1].id
    death = world_engine.kill_character(instance.id, character_id, cause_event_id=cause_event_id)
    assert death.ok is True, death.error

    world_engine.advance_tick(instance.id)
    world_engine.advance_tick(instance.id)

    assert world_engine.get_character(instance.id, character_id).lifecycle is CharacterLifecycle.DEAD
    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is ScheduledEventStatus.FAILED
    assert not any(
        event.type is EventType.CHARACTER_MOVED
        and event.actor == str(character_id)
        and event.payload.get("to") == "forest"
        for event in world_engine.get_events(instance.id)
    )
