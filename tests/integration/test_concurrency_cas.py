"""Integration: CAS по `state_version` — устаревшая версия не перезаписывает мир.

Проверяется оптимистичная блокировка: транзакция, прочитавшая версию N, не может
записать состояние, если параллельный запрос уже закоммитил N+1. Проигравший
получает ``CONFLICT`` и откатывается целиком — ни состояние, ни событие, ни
версия не теряются (11_WORLD_STATE_V1 §50).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    WorldInstanceId,
)
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.repositories.world_instance import SqlWorldInstanceRepository
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

BASE = LocationKey("base")
FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")

def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def make_character(
    world_engine: WorldEngine, instance: WorldInstance, player_id: str
) -> CharacterId:
    result = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert result.ok is True, result.error
    return CharacterId(result.payload["character_id"])


def travel_to_station(
    world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId
) -> None:
    for target in (FOREST, OLD_STATION):
        result = world_engine.move_character(
            instance.id, character_id=character_id, to_location_key=target
        )
        assert result.ok is True, result.error


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _tick_event(instance_id: WorldInstanceId, event_id: str, *, cause: str) -> Event:
    return Event(
        id=EventId(event_id),
        world_instance_id=instance_id,
        type=EventType.WORLD_TICK_ADVANCED,
        created_at=NOW,
        executed_at=NOW,
        cause=cause,
        payload={"from_tick": 0, "to_tick": 1},
    )


def test_stale_save_raises_conflict(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = make_world(world_engine)
    version = world_engine.get_instance(instance.id).state.state_version

    with uow_factory() as first, uow_factory() as second:
        first_instance = first.world_instances.get(instance.id)
        second_instance = second.world_instances.get(instance.id)
        assert first_instance.state.state_version == second_instance.state.state_version == version

        # Первая транзакция успевает закоммитить свой ход.
        first_instance.state.world_tick += 1
        first_instance.state.state_version += 1
        first.world_instances.save(first_instance, expected_state_version=version)
        first.events.append(_tick_event(instance.id, "ev_first", cause="first"))
        first.commit()

        # Вторая всё ещё считает, что версия N.
        second_instance.state.world_tick += 1
        second_instance.state.state_version += 1
        with pytest.raises(DomainError) as exc_info:
            second.world_instances.save(second_instance, expected_state_version=version)
        assert exc_info.value.code is ErrorCode.CONFLICT
        second.rollback()

    after = world_engine.get_instance(instance.id)
    assert (after.state.world_tick, after.state.state_version) == (1, 1)

    events = world_engine.get_events(instance.id)
    assert len(events) == 2  # создание мира + ход первой транзакции
    assert events[-1].id == EventId("ev_first")
    assert sum(event.type is EventType.WORLD_TICK_ADVANCED for event in events) == 1


def test_save_with_current_version_succeeds(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = make_world(world_engine)

    with uow_factory() as uow:
        loaded = uow.world_instances.get(instance.id)
        version = loaded.state.state_version
        loaded.state.world_tick += 1
        loaded.state.state_version += 1
        uow.world_instances.save(loaded, expected_state_version=version)
        uow.commit()

    after = world_engine.get_instance(instance.id)
    assert (after.state.world_tick, after.state.state_version) == (1, 1)


def test_conflict_rolls_back_state_and_event(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = make_world(world_engine)
    version = world_engine.get_instance(instance.id).state.state_version

    with uow_factory() as first, uow_factory() as second:
        first_instance = first.world_instances.get(instance.id)
        second_instance = second.world_instances.get(instance.id)

        first_instance.state.world_tick += 1
        first_instance.state.state_version += 1
        first.world_instances.save(first_instance, expected_state_version=version)
        first.commit()

        # Наш ход: состояние и событие уже подготовлены, но версия устарела.
        second_instance.state.world_tick += 1
        second_instance.state.state_version += 1
        second.events.append(_tick_event(instance.id, "ev_lost", cause="mine"))
        with pytest.raises(DomainError) as exc_info:
            second.world_instances.save(second_instance, expected_state_version=version)
        assert exc_info.value.code is ErrorCode.CONFLICT
        second.rollback()

    after = world_engine.get_instance(instance.id)
    assert (after.state.world_tick, after.state.state_version) == (1, 1)
    assert EventId("ev_lost") not in {event.id for event in world_engine.get_events(instance.id)}


@pytest.fixture()
def arm_rival(monkeypatch: pytest.MonkeyPatch) -> Callable[[WorldEngine], None]:
    """Вооружает «соперника»: первый `get` инстанса запускает чужой ход.

    Детерминированно, без sleep и реальной конкуренции: соперник коммитит свою
    транзакцию ровно в тот момент, когда наш обработчик уже прочитал версию N,
    но ещё ничего не записал.
    """
    state = {"armed": False, "fired": False}

    def arm(world_engine: WorldEngine) -> None:
        original_get = SqlWorldInstanceRepository.get

        def racing_get(self, world_instance_id):
            loaded = original_get(self, world_instance_id)
            if state["armed"] and not state["fired"]:
                state["fired"] = True
                world_engine.advance_tick(world_instance_id, cause="rival")
            return loaded

        monkeypatch.setattr(SqlWorldInstanceRepository, "get", racing_get)
        state["armed"] = True

    return arm


@pytest.mark.parametrize("action", ["advance_tick", "move_character", "share_knowledge"])
def test_stale_handler_reports_conflict_without_trace(
    world_engine: WorldEngine,
    arm_rival: Callable[[WorldEngine], None],
    action: str,
) -> None:
    """Все точки, которые сохраняют инстанс, обязаны передавать ожидаемую версию."""
    instance = make_world(world_engine)
    first = make_character(world_engine, instance, "player-a")
    second = make_character(world_engine, instance, "player-b")
    travel_to_station(world_engine, instance, first)
    travel_to_station(world_engine, instance, second)
    if action == "share_knowledge":
        assert world_engine.inspect_information(
            instance.id, character_id=first, target_key="damaged_radio"
        ).ok is True

    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    arm_rival(world_engine)

    if action == "advance_tick":
        # Методы коммита 1 поднимают доменную ошибку, а не возвращают ActionResult.
        with pytest.raises(DomainError) as exc_info:
            world_engine.advance_tick(instance.id, cause="mine")
        assert exc_info.value.code is ErrorCode.CONFLICT
    elif action == "move_character":
        result = world_engine.move_character(
            instance.id, character_id=first, to_location_key=FOREST
        )
        assert result.ok is False
        assert result.error is not None and result.error.code is ErrorCode.CONFLICT
    else:
        result = world_engine.share_knowledge(
            instance.id, sharer_id=first, receiver_id=second, information_key="damaged_radio"
        )
        assert result.ok is False
        assert result.error is not None and result.error.code is ErrorCode.CONFLICT

    # Ход соперника сохранён ровно один раз.
    after = world_engine.get_instance(instance.id)
    assert (after.state.world_tick, after.state.state_version) == (
        state_before.world_tick + 1,
        state_before.state_version + 1,
    )
    events = world_engine.get_events(instance.id)
    assert len(events) == events_before + 1
    assert events[-1].type is EventType.WORLD_TICK_ADVANCED
    assert events[-1].cause == "rival"
    assert all(event.cause != "mine" for event in events)

    # Следов нашего хода нет.
    if action == "move_character":
        assert world_engine.get_character(instance.id, first).location_key == OLD_STATION
    if action == "share_knowledge":
        assert list(world_engine.get_knowledge(instance.id, second)) == []
