"""Unit: Character — две независимые оси (lifecycle и activity)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from world_error.domain.characters.character import (
    Character,
    CharacterActivity,
    CharacterLifecycle,
)
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
OTHER_WORLD_ID = WorldInstanceId("wi_other")


def make_character() -> Character:
    return Character.create(
        id=CharacterId("ch_1"),
        world_instance_id=WORLD_ID,
        player_id="player-1",
        name="Аня",
        location_key=LocationKey("base"),
        now=NOW,
    )


def make_move_event(*, actor: str = "ch_1", world_instance_id: WorldInstanceId = WORLD_ID) -> Event:
    return Event(
        id=EventId("ev_move"),
        world_instance_id=world_instance_id,
        type=EventType.CHARACTER_MOVED,
        created_at=NOW,
        executed_at=NOW,
        actor=actor,
        target="forest",
        payload={"from": "base", "to": "forest"},
    )


def make_death_event(
    *,
    character_id: str = "ch_1",
    cause_event_id: str = "ev_cause",
    world_instance_id: WorldInstanceId = WORLD_ID,
) -> Event:
    return Event(
        id=EventId("ev_death"),
        world_instance_id=world_instance_id,
        type=EventType.DEATH_EVENT,
        created_at=NOW,
        executed_at=NOW,
        actor="system",
        target=character_id,
        cause=f"event:{cause_event_id}",
        payload={"character_id": character_id, "cause_event_id": cause_event_id},
    )


def test_created_character_is_alive_and_active() -> None:
    character = make_character()
    assert character.lifecycle is CharacterLifecycle.ALIVE
    assert character.activity is CharacterActivity.ACTIVE
    assert character.can_act() is True


def test_activity_axis_is_independent_from_lifecycle() -> None:
    character = make_character()
    character.activity = CharacterActivity.MISSING
    assert character.lifecycle is CharacterLifecycle.ALIVE
    assert character.can_act() is False
    with pytest.raises(DomainError) as exc_info:
        character.ensure_can_act()
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_dead_character_cannot_act_even_if_activity_is_active() -> None:
    character = make_character()
    character.lifecycle = CharacterLifecycle.DEAD
    character.activity = CharacterActivity.ACTIVE
    assert character.can_act() is False
    with pytest.raises(DomainError) as exc_info:
        character.ensure_can_act()
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_move_event_updates_location() -> None:
    character = make_character()
    character.apply(make_move_event())
    assert character.location_key == LocationKey("forest")
    assert character.updated_at == NOW


def test_move_event_of_another_character_is_rejected() -> None:
    character = make_character()
    with pytest.raises(DomainError) as exc_info:
        character.apply(make_move_event(actor="ch_other"))
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED
    assert character.location_key == LocationKey("base")


def test_event_from_another_instance_is_rejected() -> None:
    character = make_character()
    with pytest.raises(DomainError) as exc_info:
        character.apply(make_move_event(world_instance_id=OTHER_WORLD_ID))
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_death_event_sets_dead_and_persists_both_event_references() -> None:
    character = make_character()

    character.apply(make_death_event())

    assert character.lifecycle is CharacterLifecycle.DEAD
    assert character.death_event_id == EventId("ev_death")
    assert character.death_cause_event_id == EventId("ev_cause")
    assert character.can_act() is False


def test_death_event_without_cause_is_rejected() -> None:
    character = make_character()
    event = make_death_event(cause_event_id="")
    event = Event(
        id=event.id,
        world_instance_id=event.world_instance_id,
        type=event.type,
        created_at=event.created_at,
        target=event.target,
        payload={"character_id": "ch_1"},
    )

    with pytest.raises(DomainError) as exc_info:
        character.apply(event)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
