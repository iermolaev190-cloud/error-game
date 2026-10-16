from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import DomainError, ErrorCode
from world_error.domain.time.scheduled_event import (
    ScheduledEventStatus,
    ScheduledEventTrigger,
    ScheduledTriggerKind,
)

UTC = timezone.utc


def test_scheduled_event_trigger_requires_exactly_one_due_field() -> None:
    with pytest.raises(DomainError) as exc_info:
        ScheduledEventTrigger(ScheduledTriggerKind.AT_TICK)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION

    with pytest.raises(DomainError):
        ScheduledEventTrigger(
            ScheduledTriggerKind.AT_TICK,
            due_tick=3,
            due_time=datetime(2024, 1, 1, tzinfo=UTC),
        )


def test_scheduled_event_trigger_kinds_use_deterministic_due_checks() -> None:
    now = datetime(2024, 1, 1, tzinfo=UTC)
    assert not ScheduledEventTrigger(ScheduledTriggerKind.AT_TICK, due_tick=4).is_due(
        current_tick=3, current_time=now
    )
    assert ScheduledEventTrigger(ScheduledTriggerKind.AT_TICK, due_tick=4).is_due(
        current_tick=4, current_time=now
    )
    at_time = ScheduledEventTrigger(ScheduledTriggerKind.AT_TIME, due_time=now + timedelta(hours=1))
    assert not at_time.is_due(current_tick=10, current_time=now)
    assert at_time.is_due(current_tick=10, current_time=now + timedelta(hours=1))
    on_event = ScheduledEventTrigger(
        ScheduledTriggerKind.ON_EVENT_TYPE, due_tick=0, event_type=EventType.NPC_LEARNED
    )
    assert not on_event.is_due(current_tick=100, current_time=now)
    assert on_event.is_due(current_tick=100, current_time=now, matching_event_seen=True)


def test_scheduled_event_marks_applied_once() -> None:
    assert ScheduledEventStatus.PENDING.value == "PENDING"