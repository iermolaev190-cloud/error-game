"""Инварианты: действия валидируются и при отказе не оставляют следов.

Проверяются требования 5 и 6 коммита 2:
* MOVE в несвязанную локацию → ``INVALID_ACTION`` и полный откат;
* мёртвый персонаж не действует;
* INSPECT не выдаёт знание дважды;
* MOVE не выдаёт знание о локации.
"""

from __future__ import annotations

from typing import Callable, Tuple

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import CharacterLifecycle
from world_error.domain.shared.kernel import CharacterId, ErrorCode, LocationKey
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")
BASE = LocationKey("base")


def make_world_with_character(world_engine: WorldEngine) -> Tuple[WorldInstance, CharacterId]:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    result = world_engine.create_character(instance.id, player_id="player-1", name="Аня")
    assert result.ok is True, result.error
    return instance, CharacterId(result.payload["character_id"])


def test_move_to_unconnected_location_is_invalid_action_and_rolls_back(
    world_engine: WorldEngine,
) -> None:
    instance, character_id = make_world_with_character(world_engine)
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    # base → old_station напрямую не связаны: маршрут идёт через forest.
    result = world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=OLD_STATION
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_ACTION
    assert "not connected" in result.error.message

    character = world_engine.get_character(instance.id, character_id)
    assert character.location_key == BASE
    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )
    assert len(world_engine.get_events(instance.id)) == events_before


def test_dead_character_cannot_move_or_inspect(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance, character_id = make_world_with_character(world_engine)
    events_before = len(world_engine.get_events(instance.id))

    # Смерть как механика появится позже; здесь состояние выставляется напрямую.
    with uow_factory() as uow:
        character = uow.characters.get(instance.id, character_id)
        character.lifecycle = CharacterLifecycle.DEAD
        uow.characters.save(character)
        uow.commit()

    move_result = world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=FOREST
    )
    inspect_result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )

    assert move_result.ok is False and move_result.error.code is ErrorCode.NOT_ALLOWED
    assert inspect_result.ok is False and inspect_result.error.code is ErrorCode.NOT_ALLOWED
    assert world_engine.get_character(instance.id, character_id).location_key == BASE
    assert len(world_engine.get_events(instance.id)) == events_before


def test_inspect_from_another_location_is_not_allowed(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_ALLOWED
    assert list(world_engine.get_knowledge(instance.id, character_id)) == []
    assert len(world_engine.get_events(instance.id)) == events_before


def test_repeated_inspect_does_not_duplicate_knowledge(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=FOREST
    ).ok
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=OLD_STATION
    ).ok

    first = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )
    events_after_first = len(world_engine.get_events(instance.id))
    second = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )
    third = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )

    assert first.ok is True and first.payload["already_known"] is False
    assert second.ok is True and second.payload["already_known"] is True
    assert third.ok is True and third.payload["already_known"] is True
    assert second.event_ids == () and third.event_ids == ()
    assert len(list(world_engine.get_knowledge(instance.id, character_id))) == 1
    assert len(world_engine.get_events(instance.id)) == events_after_first


def test_move_does_not_grant_location_knowledge(world_engine: WorldEngine) -> None:
    instance, character_id = make_world_with_character(world_engine)

    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=FOREST
    ).ok
    assert list(world_engine.get_knowledge(instance.id, character_id)) == []

    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=OLD_STATION
    ).ok
    assert list(world_engine.get_knowledge(instance.id, character_id)) == []
