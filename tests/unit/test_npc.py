"""Unit: NPC — состояние, две оси статуса и применение событий."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from world_error.domain.events.event import Event, EventType
from world_error.domain.npcs.npc import Npc, NpcStatus
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    NpcId,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
OTHER_WORLD_ID = WorldInstanceId("wi_other")
NPC_ID = NpcId("npc_caretaker")


def make_npc(status: NpcStatus = NpcStatus.ACTIVE) -> Npc:
    npc = Npc.create(
        id=NPC_ID,
        world_instance_id=WORLD_ID,
        key="caretaker",
        location_key=LocationKey("base"),
        now=NOW,
    )
    npc.status = status
    return npc


def make_event(
    event_type: EventType,
    *,
    payload: dict | None = None,
    actor: str | None = "npc_caretaker",
    world_instance_id: WorldInstanceId = WORLD_ID,
    event_id: str = "ev_npc",
) -> Event:
    return Event(
        id=EventId(event_id),
        world_instance_id=world_instance_id,
        type=event_type,
        created_at=NOW,
        executed_at=NOW,
        actor=actor,
        payload=payload or {},
    )


def test_created_npc_is_active_and_bound_to_location() -> None:
    npc = make_npc()
    assert npc.status is NpcStatus.ACTIVE
    assert npc.location_key == LocationKey("base")
    assert npc.can_act() is True
    assert npc.created_at == npc.updated_at == NOW


def test_status_axis_has_only_active_and_missing() -> None:
    assert {status.value for status in NpcStatus} == {"ACTIVE", "MISSING"}


def test_missing_npc_cannot_act() -> None:
    npc = make_npc(NpcStatus.MISSING)
    assert npc.can_act() is False
    with pytest.raises(DomainError) as exc_info:
        npc.ensure_can_act()
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_move_event_changes_location() -> None:
    npc = make_npc()
    npc.apply(make_event(EventType.NPC_MOVED, payload={"from": "base", "to": "forest"}))
    assert npc.location_key == LocationKey("forest")
    assert npc.updated_at == NOW


def test_status_event_changes_status() -> None:
    npc = make_npc()
    npc.apply(make_event(EventType.NPC_STATUS_CHANGED, payload={"from": "ACTIVE", "to": "MISSING"}))
    assert npc.status is NpcStatus.MISSING
    npc.apply(make_event(EventType.NPC_STATUS_CHANGED, payload={"from": "MISSING", "to": "ACTIVE"}))
    assert npc.status is NpcStatus.ACTIVE


def test_event_of_another_actor_is_rejected() -> None:
    npc = make_npc()
    with pytest.raises(DomainError) as exc_info:
        npc.apply(make_event(EventType.NPC_MOVED, payload={"to": "forest"}, actor="npc_other"))
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED
    assert npc.location_key == LocationKey("base")


def test_event_from_another_instance_is_rejected() -> None:
    npc = make_npc()
    with pytest.raises(DomainError) as exc_info:
        npc.apply(
            make_event(
                EventType.NPC_MOVED,
                payload={"to": "forest"},
                world_instance_id=OTHER_WORLD_ID,
            )
        )
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_same_status_transition_is_rejected_by_domain() -> None:
    npc = make_npc()
    with pytest.raises(DomainError) as exc_info:
        npc.apply(
            make_event(EventType.NPC_STATUS_CHANGED, payload={"from": "ACTIVE", "to": "ACTIVE"})
        )
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_unsupported_event_type_is_rejected() -> None:
    npc = make_npc()
    with pytest.raises(DomainError) as exc_info:
        npc.apply(make_event(EventType.NPC_LEARNED, payload={"information_key": "damaged_radio"}))
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
