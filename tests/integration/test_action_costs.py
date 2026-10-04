"""Action costs advance world ticks and are represented by one range event."""

from __future__ import annotations

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.domain.time.action_cost import CostTicks
from world_error.domain.world.instance import WorldInstance


def test_move_and_inspect_costs_advance_exact_ticks_with_one_event_each(
    world_engine: WorldEngine,
) -> None:
    instance: WorldInstance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    created = world_engine.create_character(instance.id, player_id="player-a", name="Аня")
    character_id = CharacterId(created.payload["character_id"])
    start_tick = world_engine.get_instance(instance.id).state.world_tick

    moved = world_engine.move_character(
        instance.id,
        character_id=character_id,
        to_location_key=LocationKey("forest"),
        cost_ticks=CostTicks(3),
    )
    assert moved.ok is True, moved.error
    assert world_engine.get_instance(instance.id).state.world_tick == start_tick + 3

    move_cost_events = [
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.ACTION_COST_TICK_CONSUMED
    ]
    assert len(move_cost_events) == 1
    assert dict(move_cost_events[0].payload) == {
        "action": "MOVE",
        "cost": 3,
        "from_tick": start_tick,
        "to_tick": start_tick + 3,
    }

    to_station = world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=LocationKey("old_station")
    )
    assert to_station.ok is True, to_station.error
    before_inspect_tick = world_engine.get_instance(instance.id).state.world_tick
    inspected = world_engine.inspect_information(
        instance.id,
        character_id=character_id,
        target_key="damaged_radio",
        cost_ticks=CostTicks(1),
    )
    assert inspected.ok is True, inspected.error
    assert world_engine.get_instance(instance.id).state.world_tick == before_inspect_tick + 1

    cost_events = [
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.ACTION_COST_TICK_CONSUMED
    ]
    assert len(cost_events) == 2
    assert dict(cost_events[1].payload) == {
        "action": "INSPECT",
        "cost": 1,
        "from_tick": before_inspect_tick,
        "to_tick": before_inspect_tick + 1,
    }
