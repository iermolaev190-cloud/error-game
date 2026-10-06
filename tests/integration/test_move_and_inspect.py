"""Integration: MOVE и INSPECT меняют состояние только через событие."""

from __future__ import annotations

from typing import Tuple

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    DiscoveryState,
    ErrorCode,
    LocationKey,
)
from world_error.domain.world.instance import WorldInstance

FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")
BASE = LocationKey("base")
CLAIM = "Радио повреждено: корпус вскрыт, антенна сломана."


def make_world_with_character(world_engine: WorldEngine) -> Tuple[WorldInstance, CharacterId]:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    result = world_engine.create_character(instance.id, player_id="player-1", name="Аня")
    assert result.ok is True, result.error
    return instance, CharacterId(result.payload["character_id"])


def travel_to_old_station(
    world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId
) -> None:
    first = world_engine.move_character(instance.id, character_id=character_id, to_location_key=FOREST)
    assert first.ok is True, first.error
    second = world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=OLD_STATION
    )
    assert second.ok is True, second.error


def test_move_updates_location_and_moves_world_tick(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)

    result = world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=FOREST
    )

    assert result.ok is True
    assert (result.payload["from"], result.payload["to"]) == ("base", "forest")
    assert (result.payload["world_tick"], result.payload["state_version"]) == (2, 2)

    character = world_engine.get_character(instance.id, character_id)
    assert character.location_key == FOREST

    events = world_engine.get_events(instance.id)
    assert events[-1].type is EventType.CHARACTER_MOVED
    assert dict(events[-1].payload) == {"from": "base", "to": "forest"}


def test_move_marks_destination_discovered(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)
    world_engine.move_character(instance.id, character_id=character_id, to_location_key=FOREST)

    forest = next(item for item in world_engine.get_locations(instance.id) if item.key == FOREST)
    assert forest.discovery_state is DiscoveryState.DISCOVERED
    assert forest.first_visited_at is not None


def test_move_does_not_grant_knowledge(world_engine: WorldEngine) -> None:
    """Знание о локации — отдельная механика: MOVE его не выдаёт."""
    instance, character_id = make_world_with_character(world_engine)
    world_engine.move_character(instance.id, character_id=character_id, to_location_key=FOREST)

    assert list(world_engine.get_knowledge(instance.id, character_id)) == []


def test_inspect_creates_knowledge_and_marks_world_discovery(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)
    travel_to_old_station(world_engine, instance, character_id)

    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )

    assert result.ok is True
    assert result.payload["already_known"] is False
    assert result.payload["claim"] == CLAIM
    assert result.payload["claim_type"] == "FACT"
    assert result.payload["confidence"] == "LIKELY"
    assert result.payload["external_url"] == "https://example.com/archive-17"
    assert set(result.payload) == {
        "already_known",
        "information_key",
        "claim",
        "claim_type",
        "source",
        "confidence",
        "document_date",
        "world_tick",
        "state_version",
        "cost_ticks",
        "external_url",
    }
    assert result.payload["external_url"] == "https://example.com/archive-17"
    assert set(result.payload) == {
        "already_known",
        "information_key",
        "claim",
        "claim_type",
        "source",
        "confidence",
        "document_date",
        "world_tick",
        "state_version",
        "cost_ticks",
        "external_url",
    }

    knowledge = list(world_engine.get_knowledge(instance.id, character_id))
    assert len(knowledge) == 1
    assert knowledge[0].claim == CLAIM

    information = world_engine.get_information(instance.id, "damaged_radio")
    assert information.discovery_state is DiscoveryState.DISCOVERED
    assert information.discovered_by == character_id

    assert world_engine.get_events(instance.id)[-1].type is EventType.INFORMATION_DISCOVERED


def test_repeated_inspect_is_noop_without_new_event(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)
    travel_to_old_station(world_engine, instance, character_id)

    first = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )
    assert first.ok is True and first.payload["already_known"] is False

    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    second = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )

    assert second.ok is True
    assert second.payload["already_known"] is True
    assert second.payload["external_url"] == "https://example.com/archive-17"
    assert second.payload["external_url"] == "https://example.com/archive-17"
    assert second.event_ids == ()
    assert len(world_engine.get_knowledge(instance.id, character_id)) == 1
    assert len(world_engine.get_events(instance.id)) == events_before
    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )


def test_inspect_from_another_location_is_not_allowed(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)

    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_ALLOWED
    assert list(world_engine.get_knowledge(instance.id, character_id)) == []


def test_move_to_unknown_location_is_not_found(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)

    result = world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=LocationKey("nowhere")
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_FOUND


def test_inspect_unknown_information_is_not_found(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)

    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="unknown_clue"
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_FOUND
