"""Integration: event timeline points remain distinct and idempotent."""

from __future__ import annotations

from datetime import datetime, timezone

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.time.time_point import TimePoint, TimePointKind
from world_error.domain.world.instance import WorldInstance

UTC = timezone.utc


def test_occurred_discovered_reported_and_known_at_do_not_merge(
    world_engine: WorldEngine,
) -> None:
    instance: WorldInstance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    source_event = world_engine.get_events(instance.id)[-1]
    points = (
        TimePoint(source_event.id, TimePointKind.OCCURRED_AT, datetime(2024, 3, 15, 10, tzinfo=UTC)),
        TimePoint(source_event.id, TimePointKind.DISCOVERED_AT, datetime(2024, 3, 15, 15, tzinfo=UTC)),
        TimePoint(source_event.id, TimePointKind.REPORTED_AT, datetime(2024, 3, 15, 17, tzinfo=UTC)),
        TimePoint(
            source_event.id,
            TimePointKind.KNOWN_AT,
            datetime(2024, 3, 15, 20, tzinfo=UTC),
            subject_id="ch_player",
        ),
    )

    for point in points:
        result = world_engine.record_time_point(instance.id, time_point=point)
        assert result.ok is True, result.error

    assert world_engine.get_time_points(instance.id, source_event.id) == points
    recorded_events = [
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.TIME_POINT_RECORDED
    ]
    assert len(recorded_events) == 4
    assert tuple(event.time_points[0].kind for event in recorded_events) == tuple(
        point.kind for point in points
    )

    event_count = len(world_engine.get_events(instance.id))
    duplicate = world_engine.record_time_point(instance.id, time_point=points[0])
    assert duplicate.ok is True
    assert duplicate.payload["already_recorded"] is True
    assert len(world_engine.get_events(instance.id)) == event_count