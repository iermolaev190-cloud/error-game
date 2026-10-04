"""Инварианты: цепочка провенанса знания и недостижимость truth при передаче.

Проверяется требование 3a: SHARE копирует claim, а не truth; цепочка
происхождения однозвенная (source_ref), но проходимая на произвольную длину;
знание не пересекает границы WORLD INSTANCE; новый тип события идемпотентен.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.shared.kernel import (
    CharacterId,
    DiscoveryState,
    DomainError,
    ErrorCode,
    LocationKey,
    WorldInstanceId,
)
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")


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


def setup_three_at_station(
    world_engine: WorldEngine, *, chat_id: int = -1001
) -> Tuple[WorldInstance, CharacterId, CharacterId, CharacterId]:
    instance = world_engine.create_instance(telegram_chat_id=chat_id, seed=42)
    characters = [
        make_character(world_engine, instance, player_id)
        for player_id in ("player-a", "player-b", "player-c")
    ]
    for character_id in characters:
        travel_to_station(world_engine, instance, character_id)
    return instance, characters[0], characters[1], characters[2]


def inspect(
    world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId
) -> None:
    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )
    assert result.ok is True, result.error


def share(
    world_engine: WorldEngine,
    instance: WorldInstance,
    sharer: CharacterId,
    receiver: CharacterId,
) -> None:
    result = world_engine.share_knowledge(
        instance.id,
        sharer_id=sharer,
        receiver_id=receiver,
        information_key="damaged_radio",
    )
    assert result.ok is True, result.error


def only_knowledge(world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId):
    records = list(world_engine.get_knowledge(instance.id, character_id))
    assert len(records) == 1, f"ожидалась одна запись знания, получено {len(records)}"
    return records[0]


def test_chain_copies_claims_and_never_truth(
    world_engine: WorldEngine, catalog: ContentCatalog
) -> None:
    definition = catalog.information_definition("damaged_radio")
    instance, first, second, third = setup_three_at_station(world_engine)

    inspect(world_engine, instance, first)
    share(world_engine, instance, first, second)
    share(world_engine, instance, second, third)

    knowledge_first = only_knowledge(world_engine, instance, first)
    knowledge_second = only_knowledge(world_engine, instance, second)
    knowledge_third = only_knowledge(world_engine, instance, third)

    # claim один и тот же по всей цепочке, truth не появляется нигде.
    assert knowledge_first.claim == knowledge_second.claim == knowledge_third.claim
    assert knowledge_first.claim == definition.content
    assert knowledge_first.claim != definition.truth
    assert all(
        definition.truth not in record.claim
        for record in (knowledge_first, knowledge_second, knowledge_third)
    )

    # Наблюдение остаётся наблюдением, переданное знание — CLAIM/CHARACTER.
    assert knowledge_first.claim_type is ClaimType.FACT
    assert knowledge_first.source is KnowledgeSource.OBSERVATION
    assert knowledge_second.claim_type is ClaimType.CLAIM
    assert knowledge_second.source is KnowledgeSource.CHARACTER
    assert knowledge_second.source_ref == str(first)
    assert knowledge_third.claim_type is ClaimType.CLAIM
    assert knowledge_third.source is KnowledgeSource.CHARACTER
    assert knowledge_third.source_ref == str(second)


def _walk_provenance_chain(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    world_instance_id: WorldInstanceId,
    start_subject: CharacterId,
    information_id,
) -> List[Knowledge]:
    chain: List[Knowledge] = []
    visited: set[str] = set()
    with uow_factory() as uow:
        current = str(start_subject)
        while current not in visited:
            visited.add(current)
            record = uow.knowledge.find(
                world_instance_id, SubjectType.CHARACTER, current, information_id
            )
            assert record is not None, f"нет знания у {current}"
            chain.append(record)
            if record.source is not KnowledgeSource.CHARACTER:
                break
            assert record.source_ref is not None, "переданное знание обязано иметь source_ref"
            current = record.source_ref
    return chain


def test_provenance_chain_is_walkable(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance, first, second, third = setup_three_at_station(world_engine)
    inspect(world_engine, instance, first)
    share(world_engine, instance, first, second)
    share(world_engine, instance, second, third)
    information_id = world_engine.get_information(instance.id, "damaged_radio").id

    chain = _walk_provenance_chain(uow_factory, instance.id, third, information_id)

    assert [record.subject_id for record in chain] == [str(third), str(second), str(first)]
    assert chain[-1].source is KnowledgeSource.OBSERVATION
    assert chain[-1].source_ref == str(first)


def test_shared_knowledge_does_not_leak_to_another_instance(
    world_engine: WorldEngine,
) -> None:
    instance, first, second, _third = setup_three_at_station(world_engine)
    inspect(world_engine, instance, first)
    share(world_engine, instance, first, second)

    other_world = world_engine.create_instance(telegram_chat_id=-1002, seed=7)
    foreign_character = make_character(world_engine, other_world, "player-foreign")

    assert len(list(world_engine.get_knowledge(instance.id, first))) == 1
    assert len(list(world_engine.get_knowledge(instance.id, second))) == 1
    assert list(world_engine.get_knowledge(other_world.id, foreign_character)) == []
    assert (
        world_engine.get_information(other_world.id, "damaged_radio").discovery_state
        is DiscoveryState.UNDISCOVERED
    )
    # SHARE произошёл только в первом мире; второй мир его не видел.
    assert sum(
        event.type is EventType.KNOWLEDGE_SHARED
        for event in world_engine.get_events(instance.id)
    ) == 1
    assert not any(
        event.type is EventType.KNOWLEDGE_SHARED
        for event in world_engine.get_events(other_world.id)
    )


def test_duplicate_knowledge_shared_event_is_rejected(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance, first, second, _third = setup_three_at_station(world_engine)
    inspect(world_engine, instance, first)
    share(world_engine, instance, first, second)

    shared_event = next(
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.KNOWLEDGE_SHARED
    )
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    with uow_factory() as uow:
        with pytest.raises(DomainError) as exc_info:
            uow.events.append(shared_event)
        assert exc_info.value.code is ErrorCode.ALREADY_PROCESSED
        uow.rollback()

    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )
    assert len(world_engine.get_events(instance.id)) == events_before
    assert len(list(world_engine.get_knowledge(instance.id, second))) == 1
