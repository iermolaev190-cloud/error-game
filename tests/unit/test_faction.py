"""Unit: faction content definitions and instance state."""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest

from world_error.domain.events.event import Event, EventType
from world_error.domain.factions.faction import Faction, FactionDefinition, FactionStatus
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    EventId,
    FactionId,
    LocationKey,
    WorldInstanceId,
    new_faction_id,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
FACTION_ID = FactionId("fac_expedition")


def test_new_faction_id_uses_faction_namespace() -> None:
    generated = new_faction_id()
    assert generated.startswith("fac_")


def test_created_faction_has_instance_state_and_initial_status() -> None:
    faction = Faction.create(
        id=FACTION_ID,
        world_instance_id=WORLD_ID,
        key="expedition",
        location_keys=(LocationKey("base"),),
        now=NOW,
    )

    assert faction.id == FACTION_ID
    assert faction.world_instance_id == WORLD_ID
    assert faction.status is FactionStatus.STABLE
    assert faction.location_keys == (LocationKey("base"),)
    assert faction.created_at == faction.updated_at == NOW
    assert "hidden_goal" not in {field.name for field in fields(Faction)}


def test_faction_statuses_are_nonterminal_and_exclude_dissolved() -> None:
    assert len(FactionStatus) == 8
    assert "DISSOLVED" not in {status.value for status in FactionStatus}


def test_hidden_goal_is_immutable_definition_content() -> None:
    definition = FactionDefinition(
        key="expedition",
        name="Экспедиция",
        description="Группа исследователей.",
        faction_type="SCIENTIFIC",
        public_goal="Найти безопасный путь.",
        locations=(LocationKey("base"),),
        hidden_goal="Скрыть источник сигнала.",
    )

    assert definition.hidden_goal == "Скрыть источник сигнала."
    with pytest.raises(FrozenInstanceError):
        definition.hidden_goal = "Изменено"  # type: ignore[misc]


def test_status_event_changes_faction_state() -> None:
    faction = Faction.create(
        id=FACTION_ID,
        world_instance_id=WORLD_ID,
        key="expedition",
        location_keys=(),
        now=NOW,
    )
    event = Event(
        id=EventId("ev_status"),
        world_instance_id=WORLD_ID,
        type=EventType.FACTION_STATUS_CHANGED,
        created_at=NOW,
        executed_at=NOW,
        actor=str(FACTION_ID),
        payload={"from": "STABLE", "to": "CONFLICT"},
    )

    faction.apply(event)

    assert faction.status is FactionStatus.CONFLICT
    assert faction.updated_at == NOW
    with pytest.raises(DomainError) as exc_info:
        faction.apply(event)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION