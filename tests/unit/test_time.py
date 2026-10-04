from __future__ import annotations

from datetime import datetime, timedelta, timezone

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import EventId, WorldInstanceId
from world_error.domain.time.time_point import TimePoint, TimePointKind
from world_error.domain.time.world_time import WorldTime

UTC = timezone.utc


def test_world_time_is_computed_lazily_from_anchor_and_scale() -> None:
    anchor_world = datetime(2024, 3, 15, 12, tzinfo=UTC)
    anchor_real = datetime(2026, 10, 4, 12, tzinfo=UTC)
    world_time = WorldTime(anchor_world, anchor_real, time_scale=2.0)

    assert world_time.at(anchor_real + timedelta(minutes=5)) == anchor_world + timedelta(minutes=10)
    assert world_time.anchor_world_time == anchor_world
    assert world_time.anchor_real_time == anchor_real


def test_world_time_stops_while_paused_and_reanchors_on_resume() -> None:
    anchor_world = datetime(2024, 3, 15, 12, tzinfo=UTC)
    anchor_real = datetime(2026, 10, 4, 12, tzinfo=UTC)
    paused_at = anchor_real + timedelta(hours=2)
    world_time = WorldTime(anchor_world, anchor_real)

    paused = world_time.pause(paused_at)
    assert paused.at(paused_at + timedelta(days=3), running=False) == anchor_world + timedelta(hours=2)
    resumed = paused.resume(paused_at + timedelta(days=3))
    assert resumed.at(paused_at + timedelta(days=3, minutes=1)) == (
        anchor_world + timedelta(hours=2, minutes=1)
    )


def test_distinct_event_time_points_are_preserved_in_metadata() -> None:
    event = Event(
        id=EventId("ev_test"),
        world_instance_id=WorldInstanceId("wi_test"),
        type=EventType.NPC_STATUS_CHANGED,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    points = (
        TimePoint(EventId("ev_test"), TimePointKind.OCCURRED_AT, datetime(2024, 1, 1, 10, tzinfo=UTC)),
        TimePoint(EventId("ev_test"), TimePointKind.DISCOVERED_AT, datetime(2024, 1, 1, 15, tzinfo=UTC)),
        TimePoint(
            EventId("ev_test"),
            TimePointKind.KNOWN_AT,
            datetime(2024, 1, 1, 20, tzinfo=UTC),
            subject_id="ch_player",
        ),
    )
    for point in points:
        event = event.with_time_point(point)

    assert event.time_points == points