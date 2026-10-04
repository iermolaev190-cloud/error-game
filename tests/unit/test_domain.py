"""Unit-тесты domain: переходы состояния и правило A коммита 1.

Правило A: ``WORLD_INSTANCE_CREATED`` пишется в журнал, ``state_version``
созданного инстанса = 0; версия растёт только событиями, применёнными к уже
существующему инстансу.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import DomainError, ErrorCode, EventId, WorldInstanceId
from world_error.domain.world.instance import (
    InstanceEnvironment,
    InstanceLifecycle,
    WorldInstance,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
INSTANCE_ID = WorldInstanceId("wi_test")
OTHER_INSTANCE_ID = WorldInstanceId("wi_other")


def make_instance() -> WorldInstance:
    return WorldInstance.create(
        id=INSTANCE_ID,
        telegram_chat_id=-1001,
        seed=42,
        environment=InstanceEnvironment.TEST,
        now=NOW,
    )


def make_event(
    event_type: EventType,
    *,
    payload: dict[str, Any] | None = None,
    instance_id: WorldInstanceId = INSTANCE_ID,
    event_id: str = "ev_test",
) -> Event:
    return Event(
        id=EventId(event_id),
        world_instance_id=instance_id,
        type=event_type,
        created_at=NOW,
        executed_at=NOW,
        payload=payload or {},
    )


def test_created_instance_has_zero_state_version() -> None:
    instance = make_instance()
    assert instance.state.state_version == 0
    assert instance.state.world_tick == 0
    assert instance.lifecycle is InstanceLifecycle.ACTIVE
    assert instance.environment is InstanceEnvironment.TEST


def test_created_event_does_not_bump_state_version() -> None:
    instance = make_instance()
    instance.apply(make_event(EventType.WORLD_INSTANCE_CREATED))
    assert instance.state.state_version == 0
    assert instance.state.world_tick == 0


def test_tick_event_increments_tick_and_state_version() -> None:
    instance = make_instance()
    instance.apply(make_event(EventType.WORLD_TICK_ADVANCED, payload={"from_tick": 0, "to_tick": 1}))
    assert (instance.state.world_tick, instance.state.state_version) == (1, 1)


def test_status_change_increments_state_version() -> None:
    instance = make_instance()
    instance.apply(
        make_event(EventType.WORLD_INSTANCE_STATUS_CHANGED, payload={"from": "ACTIVE", "to": "PAUSED"})
    )
    assert instance.lifecycle is InstanceLifecycle.PAUSED
    assert instance.state.state_version == 1


def test_illegal_lifecycle_transition_is_rejected() -> None:
    instance = make_instance()
    instance.apply(
        make_event(
            EventType.WORLD_INSTANCE_STATUS_CHANGED,
            payload={"from": "ACTIVE", "to": "ARCHIVED"},
            event_id="ev_archive",
        )
    )
    assert instance.state.state_version == 1

    with pytest.raises(DomainError) as exc_info:
        instance.apply(
            make_event(
                EventType.WORLD_INSTANCE_STATUS_CHANGED,
                payload={"from": "ARCHIVED", "to": "ACTIVE"},
                event_id="ev_restore",
            )
        )

    assert exc_info.value.code is ErrorCode.INVALID_ACTION
    assert instance.lifecycle is InstanceLifecycle.ARCHIVED
    assert instance.state.state_version == 1


def test_event_from_another_instance_is_rejected() -> None:
    instance = make_instance()
    with pytest.raises(DomainError) as exc_info:
        instance.apply(make_event(EventType.WORLD_TICK_ADVANCED, instance_id=OTHER_INSTANCE_ID))
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED
    assert instance.state.state_version == 0
