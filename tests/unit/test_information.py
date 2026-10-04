"""Unit: Information — мир фиксирует обнаружение, первый нашедший не перезаписывается."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from world_error.domain.events.event import Event, EventType
from world_error.domain.information.information import Information
from world_error.domain.shared.kernel import (
    CharacterId,
    DiscoveryState,
    DomainError,
    ErrorCode,
    EventId,
    InformationId,
    LocationKey,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
OTHER_WORLD_ID = WorldInstanceId("wi_other")


def make_information() -> Information:
    return Information(
        id=InformationId("info_1"),
        world_instance_id=WORLD_ID,
        key="damaged_radio",
        location_key=LocationKey("old_station"),
        created_at=NOW,
    )


def make_discovery_event(
    *,
    actor: str = "ch_1",
    key: str = "damaged_radio",
    world_instance_id: WorldInstanceId = WORLD_ID,
) -> Event:
    return Event(
        id=EventId("ev_discover"),
        world_instance_id=world_instance_id,
        type=EventType.INFORMATION_DISCOVERED,
        created_at=NOW,
        executed_at=NOW,
        actor=actor,
        target=key,
        payload={"information_key": key},
    )


def test_information_exists_before_discovery() -> None:
    information = make_information()
    assert information.discovery_state is DiscoveryState.UNDISCOVERED
    assert information.discovered_by is None
    assert information.discovered_at is None


def test_discovery_is_recorded_in_world_state() -> None:
    information = make_information()
    information.apply(make_discovery_event())
    assert information.discovery_state is DiscoveryState.DISCOVERED
    assert information.discovered_by == CharacterId("ch_1")
    assert information.discovered_at == NOW


def test_second_discoverer_does_not_overwrite_first() -> None:
    information = make_information()
    information.apply(make_discovery_event(actor="ch_1"))
    information.apply(make_discovery_event(actor="ch_2"))
    assert information.discovered_by == CharacterId("ch_1")
    assert information.discovery_state is DiscoveryState.DISCOVERED


def test_event_for_another_information_is_rejected() -> None:
    information = make_information()
    with pytest.raises(DomainError) as exc_info:
        information.apply(make_discovery_event(key="other_clue"))
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED
    assert information.discovery_state is DiscoveryState.UNDISCOVERED


def test_event_from_another_instance_is_rejected() -> None:
    information = make_information()
    with pytest.raises(DomainError) as exc_info:
        information.apply(make_discovery_event(world_instance_id=OTHER_WORLD_ID))
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_unsupported_event_type_is_rejected() -> None:
    information = make_information()
    other_event = Event(
        id=EventId("ev_other"),
        world_instance_id=WORLD_ID,
        type=EventType.CHARACTER_MOVED,
        created_at=NOW,
        payload={"to": "old_station"},
    )
    with pytest.raises(DomainError) as exc_info:
        information.apply(other_event)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
