"""Инварианты: изоляция WORLD INSTANCE и идемпотентность событий.

Это критический тест (MASTER_SPEC §10, 19_MVP_V1_FOR_AI §25): изменение в
инстансе A не должно менять инстанс B — ни tick, ни state_version, ни журнал,
ни персонажей, ни знание.

Идемпотентность проверяется и для новых типов событий коммита 2
(``CHARACTER_MOVED``, ``INFORMATION_DISCOVERED``).
"""

from __future__ import annotations

from typing import Callable, Tuple

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    DiscoveryState,
    DomainError,
    ErrorCode,
    LocationKey,
)
from world_error.domain.world.instance import InstanceLifecycle, WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")


def make_world_with_character(
    world_engine: WorldEngine, *, chat_id: int = -1001, seed: int = 1, player_id: str = "player-1"
) -> Tuple[WorldInstance, CharacterId]:
    instance = world_engine.create_instance(telegram_chat_id=chat_id, seed=seed)
    result = world_engine.create_character(instance.id, player_id=player_id, name="Аня")
    assert result.ok is True, result.error
    return instance, CharacterId(result.payload["character_id"])


def travel_to_old_station(
    world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId
) -> None:
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=FOREST
    ).ok
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=OLD_STATION
    ).ok


# --- коммит 1: изоляция и идемпотентность инстанс-событий ------------------


def test_action_in_instance_a_does_not_touch_instance_b(world_engine: WorldEngine) -> None:
    instance_a = world_engine.create_instance(telegram_chat_id=-1001, seed=1)
    instance_b = world_engine.create_instance(telegram_chat_id=-1002, seed=2)

    world_engine.advance_tick(instance_a.id, cause="A action 1")
    world_engine.advance_tick(instance_a.id, cause="A action 2")

    after_a = world_engine.get_instance(instance_a.id)
    after_b = world_engine.get_instance(instance_b.id)

    assert (after_a.state.world_tick, after_a.state.state_version) == (2, 2)
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


def test_duplicate_tick_event_is_rejected_and_state_changes_once(
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
        loaded.state.world_tick += 1
        with pytest.raises(DomainError) as exc_info:
            uow.events.append(tick_event)
        assert exc_info.value.code is ErrorCode.ALREADY_PROCESSED
        uow.rollback()

    after = world_engine.get_instance(instance.id)
    assert (after.state.world_tick, after.state.state_version) == (1, 1)
    assert len(world_engine.get_events(instance.id)) == 2


# --- коммит 2: изоляция персонажей, мира и знания --------------------------


def test_character_and_knowledge_do_not_leak_between_instances(
    world_engine: WorldEngine,
) -> None:
    world_a, character_a = make_world_with_character(world_engine, chat_id=-1001, seed=1)
    world_b = world_engine.create_instance(telegram_chat_id=-1002, seed=2)

    travel_to_old_station(world_engine, world_a, character_a)
    discovered = world_engine.inspect_information(
        world_a.id, character_id=character_a, target_key="damaged_radio"
    )
    assert discovered.ok is True

    # Персонаж A не существует в B.
    with pytest.raises(DomainError) as exc_info:
        world_engine.get_character(world_b.id, character_a)
    assert exc_info.value.code is ErrorCode.NOT_FOUND

    # Знание A не видно из B.
    with pytest.raises(DomainError):
        world_engine.get_knowledge(world_b.id, character_a)

    # Мир B не изменился: только событие создания, информация не обнаружена.
    events_b = world_engine.get_events(world_b.id)
    assert [event.type for event in events_b] == [EventType.WORLD_INSTANCE_CREATED]
    information_b = world_engine.get_information(world_b.id, "damaged_radio")
    assert information_b.discovery_state is DiscoveryState.UNDISCOVERED
    assert information_b.discovered_by is None
    assert world_engine.get_instance(world_b.id).state.state_version == 0

    # А мир A изменился.
    assert world_engine.get_instance(world_a.id).state.state_version == 4
    assert world_engine.get_information(world_a.id, "damaged_radio").discovered_by == character_a


def test_duplicate_character_moved_event_is_rejected(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance, character_id = make_world_with_character(world_engine)
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=FOREST
    ).ok
    move_event = next(
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.CHARACTER_MOVED
    )

    with uow_factory() as uow:
        character = uow.characters.get(instance.id, character_id)
        character.location_key = OLD_STATION  # имитируем переход состояния
        with pytest.raises(DomainError) as exc_info:
            uow.events.append(move_event)
        assert exc_info.value.code is ErrorCode.ALREADY_PROCESSED
        uow.rollback()

    assert world_engine.get_character(instance.id, character_id).location_key == FOREST
    assert len(world_engine.get_events(instance.id)) == 3


def test_duplicate_information_discovered_event_is_rejected(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance, character_id = make_world_with_character(world_engine)
    travel_to_old_station(world_engine, instance, character_id)
    assert world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    ).ok

    discovery_event = next(
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.INFORMATION_DISCOVERED
    )
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    with uow_factory() as uow:
        with pytest.raises(DomainError) as exc_info:
            uow.events.append(discovery_event)
        assert exc_info.value.code is ErrorCode.ALREADY_PROCESSED
        uow.rollback()

    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )
    assert len(world_engine.get_events(instance.id)) == events_before
    assert len(world_engine.get_knowledge(instance.id, character_id)) == 1


def test_events_of_unrelated_instances_have_disjoint_ids(world_engine: WorldEngine) -> None:
    world_a, character_a = make_world_with_character(world_engine, chat_id=-1001, seed=1)
    world_b, character_b = make_world_with_character(
        world_engine, chat_id=-1002, seed=2, player_id="player-2"
    )
    travel_to_old_station(world_engine, world_a, character_a)
    travel_to_old_station(world_engine, world_b, character_b)

    ids_a = {event.id for event in world_engine.get_events(world_a.id)}
    ids_b = {event.id for event in world_engine.get_events(world_b.id)}
    assert ids_a and ids_b
    assert not (ids_a & ids_b)
    assert all(
        event.world_instance_id == world_a.id for event in world_engine.get_events(world_a.id)
    )
