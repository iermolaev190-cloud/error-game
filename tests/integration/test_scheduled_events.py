"""Integration: persistent scheduled events are pumped only when due."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    LocationKey,
    ScheduledEventId,
)
from world_error.domain.time.scheduled_event import ScheduledEventStatus, ScheduledTriggerKind
from world_error.domain.world.instance import WorldInstance


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def make_world(world_engine: WorldEngine) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=-1001, seed=42)


def test_scheduled_event_waits_until_due(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    created = world_engine.create_character(instance.id, player_id="player-a", name="Аня")
    character_id = CharacterId(created.payload["character_id"])
    cause = world_engine.get_events(instance.id)[-1].id
    due_tick = world_engine.get_instance(instance.id).state.world_tick + 3

    result = world_engine.schedule_event(
        instance.id,
        cause_event_id=cause,
        event_key="supply_arrival",
        idempotency_key="supply-arrival-1",
        trigger_kind=ScheduledTriggerKind.AT_TICK,
        due_tick=due_tick,
        payload={"location_key": "base"},
    )

    assert result.ok is True, result.error
    scheduled_id = ScheduledEventId(result.payload["scheduled_event_id"])
    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.PENDING
    )

    world_engine.advance_tick(instance.id)
    assert world_engine.get_instance(instance.id).state.world_tick < due_tick
    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.PENDING
    )

    world_engine.advance_tick(instance.id)
    scheduled = world_engine.get_scheduled_event(instance.id, scheduled_id)
    assert scheduled.status is ScheduledEventStatus.APPLIED
    assert scheduled.triggered_event_id is not None
    triggered = [
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.SCHEDULED_EVENT_TRIGGERED
    ]
    assert len(triggered) == 1
    assert triggered[0].payload["event_key"] == "supply_arrival"
    assert str(character_id) not in str(triggered[0].payload)


def test_immediate_scheduled_event_is_idempotent(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    cause = world_engine.get_events(instance.id)[-1].id
    command = {
        "cause_event_id": cause,
        "event_key": "gate_opened",
        "idempotency_key": "gate-open-1",
        "trigger_kind": ScheduledTriggerKind.IMMEDIATE,
    }

    first = world_engine.schedule_event(instance.id, **command)
    second = world_engine.schedule_event(instance.id, **command)

    assert first.ok is True, first.error
    assert second.ok is True, second.error
    assert second.payload["already_scheduled"] is True
    assert len(world_engine.list_scheduled_events(instance.id)) == 0
    assert len(
        [event for event in world_engine.get_events(instance.id) if event.type is EventType.SCHEDULED_EVENT_TRIGGERED]
    ) == 1


def test_scheduled_event_waits_for_matching_event_type(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    cause = world_engine.get_events(instance.id)[-1].id
    result = world_engine.schedule_event(
        instance.id,
        cause_event_id=cause,
        event_key="tick_notice",
        idempotency_key="tick-notice-1",
        trigger_kind=ScheduledTriggerKind.ON_EVENT_TYPE,
        trigger_event_type=EventType.WORLD_TICK_ADVANCED,
    )
    assert result.ok is True, result.error
    scheduled_id = ScheduledEventId(result.payload["scheduled_event_id"])
    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.PENDING
    )

    world_engine.advance_tick(instance.id)

    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.APPLIED
    )


def test_scheduled_events_are_instance_scoped(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine)
    world_two = world_engine.create_instance(telegram_chat_id=-1002, seed=42)
    cause = world_engine.get_events(world_one.id)[-1].id
    result = world_engine.schedule_event(
        world_one.id,
        cause_event_id=cause,
        event_key="private-arrival",
        idempotency_key="private-arrival-1",
        trigger_kind=ScheduledTriggerKind.AT_TICK,
        due_tick=100,
        payload={"location_key": "base"},
    )
    assert result.ok is True, result.error
    scheduled_id = ScheduledEventId(result.payload["scheduled_event_id"])

    assert world_engine.list_scheduled_events(world_two.id) == []
    with pytest.raises(DomainError) as exc_info:
        world_engine.get_scheduled_event(world_two.id, scheduled_id)
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_at_time_trigger_uses_world_time(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    cause = world_engine.get_events(instance.id)[-1].id
    due_time = world_engine.get_world_time(instance.id) - timedelta(seconds=1)
    result = world_engine.schedule_event(
        instance.id,
        cause_event_id=cause,
        event_key="expired-deadline",
        idempotency_key="expired-deadline-1",
        trigger_kind=ScheduledTriggerKind.AT_TIME,
        due_time=due_time,
    )
    assert result.ok is True, result.error
    scheduled_id = ScheduledEventId(result.payload["scheduled_event_id"])
    assert world_engine.get_scheduled_event(instance.id, scheduled_id).status is (
        ScheduledEventStatus.APPLIED
    )


def test_due_at_time_event_is_applied_before_next_player_action(
    uow_factory, catalog
) -> None:  # noqa: ANN001
    clock = MutableClock(datetime(2026, 10, 7, 12, tzinfo=timezone.utc))
    world_engine = WorldEngine(uow_factory=uow_factory, catalog=catalog, clock=clock)
    instance = make_world(world_engine)
    created = world_engine.create_character(instance.id, player_id="player-a", name="Аня")
    character_id = CharacterId(created.payload["character_id"])
    cause = world_engine.get_events(instance.id)[-1].id
    due_time = world_engine.get_world_time(instance.id) + timedelta(minutes=1)
    result = world_engine.schedule_event(
        instance.id,
        cause_event_id=cause,
        event_key="time-sensitive-event",
        idempotency_key="time-sensitive-event-1",
        trigger_kind=ScheduledTriggerKind.AT_TIME,
        due_time=due_time,
    )
    assert result.ok is True, result.error

    clock.value += timedelta(minutes=2)
    moved = world_engine.move_character(
        instance.id,
        character_id=character_id,
        to_location_key=LocationKey("forest"),
    )
    assert moved.ok is True, moved.error

    events = world_engine.get_events(instance.id)
    event_types = [event.type for event in events]
    scheduled_event_index = event_types.index(EventType.SCHEDULED_EVENT_TRIGGERED)
    move_event_index = event_types.index(EventType.CHARACTER_MOVED)
    assert scheduled_event_index < move_event_index


def test_pending_schedule_is_not_part_of_location_view(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    character = world_engine.create_character(instance.id, player_id="player-a", name="Аня")
    character_id = CharacterId(character.payload["character_id"])
    cause = world_engine.get_events(instance.id)[-1].id
    world_engine.schedule_event(
        instance.id,
        cause_event_id=cause,
        event_key="private_alarm",
        idempotency_key="private-alarm-1",
        trigger_kind=ScheduledTriggerKind.AT_TICK,
        due_tick=100,
        payload={"location_key": "base"},
    )

    view = world_engine.view_location(
        instance.id, observer_id=character_id, location_key="base"
    )
    assert "private_alarm" not in repr(view)
    assert "scheduled" not in repr(view).lower()
