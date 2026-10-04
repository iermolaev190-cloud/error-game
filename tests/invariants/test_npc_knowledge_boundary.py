"""Инварианты: граница знания NPC, изоляция миров и право на ошибку.

05_NPCS §26: NPC не знает того, чего не видел, не слышал и не получил от другого
источника. §2–§4: NPC может ошибаться, а его слова — не истина.
"""

from __future__ import annotations

from typing import Tuple

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import ClaimType, KnowledgeSource, SubjectType
from world_error.domain.npcs.npc import Npc
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


def npc_by_key(world_engine: WorldEngine, instance: WorldInstance, key: str) -> Npc:
    return next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == key)


def make_character(
    world_engine: WorldEngine, instance: WorldInstance, player_id: str = "player-a"
) -> CharacterId:
    result = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert result.ok is True, result.error
    return CharacterId(result.payload["character_id"])


def travel_to_station(
    world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId
) -> None:
    for target in (FOREST, OLD_STATION):
        assert world_engine.move_character(
            instance.id, character_id=character_id, to_location_key=target
        ).ok is True


def test_npc_knows_nothing_until_told(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")
    scout = npc_by_key(world_engine, instance, "scout")

    assert list(world_engine.get_npc_knowledge(instance.id, mechanic.id)) == []
    assert list(world_engine.get_npc_knowledge(instance.id, scout.id)) == []

    told = world_engine.npc_learn(instance.id, npc_id=mechanic.id, information_key=INFO_KEY)
    assert told.ok is True

    assert len(list(world_engine.get_npc_knowledge(instance.id, mechanic.id))) == 1
    # Второму NPC знание не передавалось — он по-прежнему ничего не знает.
    assert list(world_engine.get_npc_knowledge(instance.id, scout.id)) == []


def test_player_knowledge_does_not_reach_npc(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    character = make_character(world_engine, instance)
    travel_to_station(world_engine, instance, character)
    assert world_engine.inspect_information(
        instance.id, character_id=character, target_key=INFO_KEY
    ).ok is True

    mechanic = npc_by_key(world_engine, instance, "mechanic")
    assert len(list(world_engine.get_knowledge(instance.id, character))) == 1
    assert list(world_engine.get_npc_knowledge(instance.id, mechanic.id)) == []


def test_npc_knowledge_does_not_reach_player(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    character = make_character(world_engine, instance)
    mechanic = npc_by_key(world_engine, instance, "mechanic")
    assert world_engine.npc_learn(
        instance.id, npc_id=mechanic.id, information_key=INFO_KEY, claim="Своя версия механика."
    ).ok is True

    assert len(list(world_engine.get_npc_knowledge(instance.id, mechanic.id))) == 1
    assert list(world_engine.get_knowledge(instance.id, character)) == []


def test_npc_knowledge_does_not_cross_instances(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    npc_one = npc_by_key(world_engine, world_one, "mechanic")
    npc_two = npc_by_key(world_engine, world_two, "mechanic")

    assert world_engine.npc_observe_information(
        world_one.id, npc_id=npc_one.id, information_key=INFO_KEY
    ).ok is True

    assert len(list(world_engine.get_npc_knowledge(world_one.id, npc_one.id))) == 1
    assert list(world_engine.get_npc_knowledge(world_two.id, npc_two.id)) == []
    assert (
        world_engine.get_information(world_two.id, INFO_KEY).discovery_state
        is DiscoveryState.UNDISCOVERED
    )
    assert [event.type for event in world_engine.get_events(world_two.id)] == [
        EventType.WORLD_INSTANCE_CREATED
    ]


def test_npc_of_another_instance_is_invisible(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    npc_one = npc_by_key(world_engine, world_one, "caretaker")

    with pytest.raises(DomainError) as exc_info:
        world_engine.get_npc(world_two.id, npc_one.id)
    assert exc_info.value.code is ErrorCode.NOT_FOUND

    observer = make_character(world_engine, world_two)
    view = world_engine.view_location(world_two.id, observer_id=observer, location_key=BASE)
    assert npc_one.id not in {presence.npc_id for presence in view.npcs}
    assert {presence.name for presence in view.npcs} == {"Смотритель"}


def test_npc_belief_can_contradict_truth_without_leaking_it(
    world_engine: WorldEngine, catalog
) -> None:
    definition = catalog.information_definition(INFO_KEY)
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")

    assert world_engine.npc_learn(
        instance.id,
        npc_id=mechanic.id,
        information_key=INFO_KEY,
        claim_type=ClaimType.BELIEF,
        source=KnowledgeSource.RUMOR,
        claim="Радио сломано давно, никто не приходил.",
    ).ok is True

    knowledge = list(world_engine.get_npc_knowledge(instance.id, mechanic.id))
    assert len(knowledge) == 1
    assert knowledge[0].subject_type is SubjectType.NPC
    assert knowledge[0].claim_type is ClaimType.BELIEF
    assert knowledge[0].claim != definition.truth
    assert all(definition.truth not in record.claim for record in knowledge)


def test_npc_knowledge_is_scoped_to_its_subject(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")
    scout = npc_by_key(world_engine, instance, "scout")

    assert world_engine.npc_learn(
        instance.id, npc_id=mechanic.id, information_key=INFO_KEY
    ).ok is True

    mechanic_knowledge = list(world_engine.get_npc_knowledge(instance.id, mechanic.id))
    scout_knowledge = list(world_engine.get_npc_knowledge(instance.id, scout.id))

    assert len(mechanic_knowledge) == 1
    assert mechanic_knowledge[0].subject_id == str(mechanic.id)
    assert scout_knowledge == []
