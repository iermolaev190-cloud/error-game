"""Unit-тесты domain: переходы состояния, учёт событий и правило A.

Правило A: ``WORLD_INSTANCE_CREATED`` пишется в журнал, ``state_version``
созданного инстанса = 0; версия растёт только событиями, применёнными к уже
существующему инстансу.

Учёт событий (коммит 2): инстанс-события обрабатывает ``apply``,
события-действия — ``register_applied_event``; у обоих растут tick и version.
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
CONTENT_VERSION = "v1"


def make_instance() -> WorldInstance:
    return WorldInstance.create(
        id=INSTANCE_ID,
        telegram_chat_id=-1001,
        seed=42,
        content_version=CONTENT_VERSION,
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
    assert instance.content_version == CONTENT_VERSION


def test_content_version_is_not_state_version() -> None:
    """content_version — версия определений контента, а не состояние мира."""
    instance = make_instance()
    instance.register_applied_event(make_event(EventType.CHARACTER_MOVED, payload={"to": "forest"}))
    assert instance.content_version == CONTENT_VERSION
    assert instance.state.state_version == 1


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


def test_action_event_is_registered_and_moves_tick() -> None:
    instance = make_instance()
    instance.register_applied_event(
        make_event(EventType.CHARACTER_MOVED, payload={"from": "base", "to": "forest"})
    )
    assert (instance.state.world_tick, instance.state.state_version) == (1, 1)


def test_apply_rejects_action_event() -> None:
    instance = make_instance()
    with pytest.raises(DomainError) as exc_info:
        instance.apply(make_event(EventType.CHARACTER_MOVED, payload={"to": "forest"}))
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
    assert instance.state.state_version == 0


def test_register_applied_event_rejects_instance_event() -> None:
    instance = make_instance()
    with pytest.raises(DomainError) as exc_info:
        instance.register_applied_event(make_event(EventType.WORLD_TICK_ADVANCED))
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
    assert (instance.state.world_tick, instance.state.state_version) == (0, 0)


@pytest.mark.parametrize("lifecycle", [InstanceLifecycle.PAUSED, InstanceLifecycle.ARCHIVED])
def test_inactive_instance_rejects_action_events(lifecycle: InstanceLifecycle) -> None:
    instance = make_instance()
    instance.apply(
        make_event(
            EventType.WORLD_INSTANCE_STATUS_CHANGED,
            payload={"from": "ACTIVE", "to": lifecycle.value},
            event_id="ev_status",
        )
    )
    state_before = (instance.state.world_tick, instance.state.state_version)

    with pytest.raises(DomainError) as exc_info:
        instance.register_applied_event(
            make_event(
                EventType.CHARACTER_MOVED,
                payload={"from": "base", "to": "forest"},
                event_id="ev_move",
            )
        )

    assert exc_info.value.code is ErrorCode.INVALID_ACTION
    assert (instance.state.world_tick, instance.state.state_version) == state_before
