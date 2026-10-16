"""Инварианты мультиплеера: 3 игрока в одном INSTANCE и 2 игрока × 2 INSTANCE.

Проверяется главный вопрос MVP (19_MVP_V1_FOR_AI §24–28): несколько игроков живут
в одном мире, знание у каждого своё, и миры не смешиваются даже при одинаковых
player_id.
"""

from __future__ import annotations

from typing import Tuple

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import ClaimType, KnowledgeSource
from world_error.domain.shared.kernel import (
    CharacterId,
    DiscoveryState,
    DomainError,
    ErrorCode,
    LocationKey,
)
from world_error.domain.world.instance import WorldInstance

BASE = LocationKey("base")
FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")
INFO_KEY = "damaged_radio"


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


def inspect(world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId) -> None:
    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key=INFO_KEY
    )
    assert result.ok is True, result.error


def knowledge_of(world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId):
    return list(world_engine.get_knowledge(instance.id, character_id))


def setup_three_at_station(
    world_engine: WorldEngine,
) -> Tuple[WorldInstance, CharacterId, CharacterId, CharacterId]:
    instance = make_world(world_engine)
    players = [
        make_character(world_engine, instance, player_id)
        for player_id in ("player-a", "player-b", "player-c")
    ]
    for character_id in players:
        travel_to_station(world_engine, instance, character_id)
    return instance, players[0], players[1], players[2]


def test_three_players_have_asymmetric_knowledge(world_engine: WorldEngine) -> None:
    instance, first, second, third = setup_three_at_station(world_engine)

    inspect(world_engine, instance, first)
    assert len(knowledge_of(world_engine, instance, first)) == 1
    assert knowledge_of(world_engine, instance, second) == []
    assert knowledge_of(world_engine, instance, third) == []
    assert world_engine.get_information(instance.id, INFO_KEY).discovered_by == first

    inspect(world_engine, instance, second)
    assert len(knowledge_of(world_engine, instance, first)) == 1
    assert len(knowledge_of(world_engine, instance, second)) == 1
    assert knowledge_of(world_engine, instance, third) == []

    knowledge_first = knowledge_of(world_engine, instance, first)[0]
    knowledge_second = knowledge_of(world_engine, instance, second)[0]
    assert knowledge_first.subject_id == str(first)
    assert knowledge_second.subject_id == str(second)
    assert knowledge_first.source is KnowledgeSource.OBSERVATION
    assert knowledge_second.source is KnowledgeSource.OBSERVATION

    shared = world_engine.share_knowledge(
        instance.id, sharer_id=first, receiver_id=third, information_key=INFO_KEY
    )
    assert shared.ok is True

    knowledge_third = knowledge_of(world_engine, instance, third)
    assert len(knowledge_third) == 1
    assert knowledge_third[0].subject_id == str(third)
    assert knowledge_third[0].claim_type is ClaimType.CLAIM
    assert knowledge_third[0].source is KnowledgeSource.CHARACTER
    assert knowledge_third[0].source_ref == str(first)
    # Знание второго игрока от передачи не изменилось.
    assert len(knowledge_of(world_engine, instance, second)) == 1
    # Первый нашедший не перезаписан.
    assert world_engine.get_information(instance.id, INFO_KEY).discovered_by == first


def test_two_players_in_two_instances_do_not_mix(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)

    one_a = make_character(world_engine, world_one, "player-1")
    one_b = make_character(world_engine, world_one, "player-2")
    two_a = make_character(world_engine, world_two, "player-1")
    two_b = make_character(world_engine, world_two, "player-2")

    # Один и тот же player_id в двух мирах — два независимых персонажа.
    assert len({one_a, one_b, two_a, two_b}) == 4

    travel_to_station(world_engine, world_one, one_a)
    travel_to_station(world_engine, world_one, one_b)
    inspect(world_engine, world_one, one_a)
    assert world_engine.share_knowledge(
        world_one.id, sharer_id=one_a, receiver_id=one_b, information_key=INFO_KEY
    ).ok is True

    # Первый мир изменился.
    assert len(knowledge_of(world_engine, world_one, one_a)) == 1
    assert len(knowledge_of(world_engine, world_one, one_b)) == 1

    # Второй мир не видел ничего из этого.
    assert knowledge_of(world_engine, world_two, two_a) == []
    assert knowledge_of(world_engine, world_two, two_b) == []
    assert (
        world_engine.get_information(world_two.id, INFO_KEY).discovery_state
        is DiscoveryState.UNDISCOVERED
    )
    assert [event.type for event in world_engine.get_events(world_two.id)] == [
        EventType.WORLD_INSTANCE_CREATED,
        EventType.CHARACTER_CREATED,
        EventType.CHARACTER_CREATED,
    ]
    assert world_engine.get_instance(world_two.id).state.state_version == 2

    # Персонаж одного мира не виден в другом.
    with pytest.raises(DomainError) as exc_info:
        world_engine.get_character(world_two.id, one_a)
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_location_view_does_not_show_other_instance_characters(
    world_engine: WorldEngine,
) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    observer = make_character(world_engine, world_one, "player-a")
    make_character(world_engine, world_two, "player-b")

    view = world_engine.view_location(world_one.id, observer_id=observer, location_key=BASE)

    assert [presence.character_id for presence in view.characters] == [str(observer)]
