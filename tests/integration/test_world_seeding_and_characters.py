"""Integration: создание мира материализует instance-состояние из контента."""

from __future__ import annotations

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.shared.kernel import (
    CharacterId,
    DiscoveryState,
    DomainError,
    ErrorCode,
    LocationKey,
)


def test_world_creation_seeds_locations_and_information(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)

    assert instance.content_version == "v1"
    assert (instance.state.world_tick, instance.state.state_version) == (0, 0)

    locations = world_engine.get_locations(instance.id)
    assert {str(item.key) for item in locations} == {"base", "forest", "old_station"}
    assert all(item.discovery_state is DiscoveryState.UNDISCOVERED for item in locations)

    information = world_engine.get_information(instance.id, "damaged_radio")
    assert information.discovery_state is DiscoveryState.UNDISCOVERED
    assert information.discovered_by is None
    assert information.discovered_at is None

    factions = world_engine.get_factions(instance.id)
    assert {faction.key for faction in factions} == {"council", "expedition", "union"}
    expedition = next(faction for faction in factions if faction.key == "expedition")
    assert expedition.location_keys == (LocationKey("base"), LocationKey("forest"))

    events = world_engine.get_events(instance.id)
    assert [event.type.value for event in events] == ["WORLD_INSTANCE_CREATED"]


def test_character_creation_roundtrip(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    result = world_engine.create_character(instance.id, player_id="player-1", name="Аня")

    assert result.ok is True
    assert result.payload["location_key"] == "base"
    assert result.payload["lifecycle"] == "ALIVE"
    assert result.payload["activity"] == "ACTIVE"
    assert (result.payload["world_tick"], result.payload["state_version"]) == (1, 1)

    character = world_engine.get_character(
        instance.id, CharacterId(result.payload["character_id"])
    )
    assert character.player_id == "player-1"
    assert character.name == "Аня"
    assert character.location_key == LocationKey("base")

    base = next(
        item for item in world_engine.get_locations(instance.id) if item.key == LocationKey("base")
    )
    assert base.discovery_state is DiscoveryState.DISCOVERED

    events = world_engine.get_events(instance.id)
    assert [event.type.value for event in events] == ["WORLD_INSTANCE_CREATED", "CHARACTER_CREATED"]


def test_second_alive_character_for_same_player_is_rejected(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    first = world_engine.create_character(instance.id, player_id="player-1", name="Аня")
    assert first.ok is True

    second = world_engine.create_character(instance.id, player_id="player-1", name="Второй")

    assert second.ok is False
    assert second.error is not None
    assert second.error.code is ErrorCode.NOT_ALLOWED
    assert len(world_engine.get_events(instance.id)) == 2
    assert world_engine.get_instance(instance.id).state.state_version == 1


def test_character_cannot_start_in_unknown_location(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    result = world_engine.create_character(
        instance.id, player_id="player-1", name="Аня", location_key=LocationKey("nowhere")
    )
    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_FOUND
    assert len(world_engine.get_events(instance.id)) == 1


def test_character_of_another_instance_is_not_visible(world_engine: WorldEngine) -> None:
    instance_a = world_engine.create_instance(telegram_chat_id=-1001, seed=1)
    instance_b = world_engine.create_instance(telegram_chat_id=-1002, seed=2)
    created = world_engine.create_character(instance_a.id, player_id="player-1", name="Аня")
    character_id = CharacterId(created.payload["character_id"])

    with pytest.raises(DomainError) as exc_info:
        world_engine.get_character(instance_b.id, character_id)
    assert exc_info.value.code is ErrorCode.NOT_FOUND
