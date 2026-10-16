"""Integration: WORLD_TIME is lazy and freezes across pause/resume."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.shared.kernel import ErrorCode
from world_error.domain.world.instance import InstanceLifecycle

UTC = timezone.utc


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def test_world_time_is_lazy_and_pause_resume_reanchors(
    uow_factory, catalog
) -> None:  # noqa: ANN001
    clock = MutableClock(datetime(2026, 10, 4, 12, tzinfo=UTC))
    world_engine = WorldEngine(uow_factory=uow_factory, catalog=catalog, clock=clock)
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    world_anchor = instance.state.current_time
    real_anchor = instance.anchor_real_time

    clock.value += timedelta(minutes=10)
    assert world_engine.get_world_time(instance.id) == world_anchor + timedelta(minutes=10)
    unchanged = world_engine.get_instance(instance.id)
    assert unchanged.state.current_time == world_anchor
    assert unchanged.anchor_real_time == real_anchor
    assert unchanged.state.world_tick == 0

    world_engine.advance_tick(instance.id)
    advanced = world_engine.get_instance(instance.id)
    assert advanced.state.current_time == world_anchor + timedelta(minutes=10)
    assert advanced.anchor_real_time == clock.value

    clock.value += timedelta(minutes=5)
    world_engine.change_status(instance.id, to=InstanceLifecycle.PAUSED)
    paused = world_engine.get_instance(instance.id)
    frozen_world_time = paused.state.current_time
    clock.value += timedelta(days=2)
    assert world_engine.get_world_time(instance.id) == frozen_world_time
    assert world_engine.get_instance(instance.id).anchor_real_time == paused.anchor_real_time

    world_engine.change_status(instance.id, to=InstanceLifecycle.ACTIVE)
    clock.value += timedelta(minutes=1)
    assert world_engine.get_world_time(instance.id) == frozen_world_time + timedelta(minutes=1)


def test_paused_instance_rejects_character_creation_without_state_change(
    uow_factory, catalog
) -> None:  # noqa: ANN001
    clock = MutableClock(datetime(2026, 10, 4, 12, tzinfo=UTC))
    world_engine = WorldEngine(uow_factory=uow_factory, catalog=catalog, clock=clock)
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    world_engine.change_status(instance.id, to=InstanceLifecycle.PAUSED)
    paused = world_engine.get_instance(instance.id)
    events_before = world_engine.get_events(instance.id)

    result = world_engine.create_character(
        instance.id, player_id="player-a", name="Аня"
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_ACTION
    assert world_engine.find_active_character_for_player(instance.id, "player-a") is None
    current = world_engine.get_instance(instance.id)
    assert (current.state.world_tick, current.state.state_version) == (
        paused.state.world_tick,
        paused.state.state_version,
    )
    assert world_engine.get_events(instance.id) == events_before