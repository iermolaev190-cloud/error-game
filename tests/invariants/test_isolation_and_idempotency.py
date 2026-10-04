"""Инварианты коммита 1: изоляция WORLD INSTANCE и идемпотентность событий.

Это критический тест (MASTER_SPEC §10, 19_MVP_V1_FOR_AI §25): изменение в
инстансе A не должно менять инстанс B — ни tick, ни state_version, ни журнал.
"""

from __future__ import annotations

from typing import Callable

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import DomainError, ErrorCode
from world_error.domain.world.instance import InstanceLifecycle
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


def test_action_in_instance_a_does_not_touch_instance_b(world_engine: WorldEngine) -> None:
    instance_a = world_engine.create_instance(telegram_chat_id=-1001, seed=1)
    instance_b = world_engine.create_instance(telegram_chat_id=-1002, seed=2)

    world_engine.advance_tick(instance_a.id, cause="A action 1")
    world_engine.advance_tick(instance_a.id, cause="A action 2")

    after_a = world_engine.get_instance(instance_a.id)
    after_b = world_engine.get_instance(instance_b.id)

    # A изменился...
    assert (after_a.state.world_tick, after_a.state.state_version) == (2, 2)
    # ...B — нет.
    assert (after_b.state.world_tick, after_b.state.state_version) == (0, 0)
    assert after_b.id != after_a.id
    assert after_b.telegram_chat_id == -1002
    assert after_b.seed == 2


def test_event_log_does_not_leak_between_instances(world_engine: WorldEngine) -> None:
    instance_a = world_engine.create_instance(telegram_chat_id=-1001, seed=1)
    instance_b = world_engine.create_instance(telegram_chat_id=-1002, seed=2)
    world_engine.advance_tick(instance_a.id, cause="A action")

    events_a = list(world_engine.get_events(instance_a.id))
    events_b = list(world_engine.get_events(instance_b.id))

    assert {event.world_instance_id for event in events_a} == {instance_a.id}
    assert {event.world_instance_id for event in events_b} == {instance_b.id}
    assert not ({event.id for event in events_a} & {event.id for event in events_b})
    assert [event.type for event in events_b] == [EventType.WORLD_INSTANCE_CREATED]
    assert len(events_a) == 2


def test_lifecycle_change_does_not_leak_between_instances(world_engine: WorldEngine) -> None:
    instance_a = world_engine.create_instance(telegram_chat_id=-1001, seed=1)
    instance_b = world_engine.create_instance(telegram_chat_id=-1002, seed=2)

    world_engine.change_status(instance_a.id, to=InstanceLifecycle.PAUSED, cause="pause A")

    assert world_engine.get_instance(instance_a.id).lifecycle is InstanceLifecycle.PAUSED
    assert world_engine.get_instance(instance_b.id).lifecycle is InstanceLifecycle.ACTIVE


def test_duplicate_event_id_is_rejected_and_state_changes_once(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=7)
    world_engine.advance_tick(instance.id, cause="first")
    tick_event = next(
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.WORLD_TICK_ADVANCED
    )

    with uow_factory() as uow:
        loaded = uow.world_instances.get(instance.id)
        loaded.state.world_tick += 1  # имитируем переход состояния
        with pytest.raises(DomainError) as exc_info:
            uow.events.append(tick_event)  # тот же event_id в том же инстансе
        assert exc_info.value.code is ErrorCode.ALREADY_PROCESSED
        uow.rollback()

    after = world_engine.get_instance(instance.id)
    assert (after.state.world_tick, after.state.state_version) == (1, 1)
    assert len(world_engine.get_events(instance.id)) == 2
