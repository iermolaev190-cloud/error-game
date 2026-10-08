"""Integration: SHARE — передача знания, no-op и отказы без следов."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Tuple

import pytest
from sqlalchemy.exc import IntegrityError

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.shared.kernel import (
    CharacterId,
    ErrorCode,
    KnowledgeId,
    LocationKey,
)
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")
CLAIM = "Радио повреждено: корпус вскрыт, антенна сломана."
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


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


def setup_two_at_station(
    world_engine: WorldEngine,
) -> Tuple[WorldInstance, CharacterId, CharacterId]:
    instance = make_world(world_engine)
    sharer = make_character(world_engine, instance, "player-a")
    receiver = make_character(world_engine, instance, "player-b")
    travel_to_station(world_engine, instance, sharer)
    travel_to_station(world_engine, instance, receiver)
    return instance, sharer, receiver


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
    information_key: str = "damaged_radio",
):
    return world_engine.share_knowledge(
        instance.id,
        sharer_id=sharer,
        receiver_id=receiver,
        information_key=information_key,
    )


def test_share_creates_claim_knowledge_with_provenance(world_engine: WorldEngine) -> None:
    instance, sharer, receiver = setup_two_at_station(world_engine)
    inspect(world_engine, instance, sharer)
    sharer_knowledge = list(world_engine.get_knowledge(instance.id, sharer))[0]
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    result = share(world_engine, instance, sharer, receiver)

    assert result.ok is True, result.error
    assert result.payload["already_known"] is False
    assert result.payload["claim"] == sharer_knowledge.claim == CLAIM
    assert result.payload["claim_type"] == "CLAIM"
    assert result.payload["source"] == "CHARACTER"
    assert result.payload["source_ref"] == str(sharer)
    assert result.payload["confidence"] == "LIKELY"

    receiver_knowledge = list(world_engine.get_knowledge(instance.id, receiver))
    assert len(receiver_knowledge) == 1
    shared = receiver_knowledge[0]
    assert shared.claim == CLAIM
    assert shared.claim_type is ClaimType.CLAIM
    assert shared.source is KnowledgeSource.CHARACTER
    assert shared.source_ref == str(sharer)
    assert shared.subject_id == str(receiver)
    assert shared.information_id == sharer_knowledge.information_id
    assert shared.confidence is KnowledgeConfidence.LIKELY

    # Знание sharer'а не изменилось.
    assert list(world_engine.get_knowledge(instance.id, sharer))[0] == sharer_knowledge

    events = world_engine.get_events(instance.id)
    assert len(events) == events_before + 1
    assert events[-1].type is EventType.KNOWLEDGE_SHARED
    assert events[-1].actor == str(sharer)
    assert events[-1].target == str(receiver)
    state_after = world_engine.get_instance(instance.id).state
    assert state_after.state_version == state_before.state_version + 1
    assert state_after.world_tick == state_before.world_tick + 1


def test_shared_knowledge_is_persisted(
    world_engine: WorldEngine, uow_factory
) -> None:
    instance, sharer, receiver = setup_two_at_station(world_engine)
    inspect(world_engine, instance, sharer)
    assert share(world_engine, instance, sharer, receiver).ok is True

    information_id = world_engine.get_information(instance.id, "damaged_radio").id
    with uow_factory() as uow:
        stored = uow.knowledge.find(
            instance.id, SubjectType.CHARACTER, str(receiver), information_id
        )

    assert stored is not None
    assert stored.claim == CLAIM
    assert stored.claim_type is ClaimType.CLAIM
    assert stored.source is KnowledgeSource.CHARACTER
    assert stored.source_ref == str(sharer)
    assert stored.confidence is KnowledgeConfidence.LIKELY


def test_repeated_share_is_noop_without_event(world_engine: WorldEngine) -> None:
    instance, sharer, receiver = setup_two_at_station(world_engine)
    inspect(world_engine, instance, sharer)
    assert share(world_engine, instance, sharer, receiver).ok is True

    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    second = share(world_engine, instance, sharer, receiver)
    third = share(world_engine, instance, sharer, receiver)

    assert second.ok is True and second.payload["already_known"] is True
    assert third.ok is True and third.payload["already_known"] is True
    assert second.event_ids == () and third.event_ids == ()
    assert len(list(world_engine.get_knowledge(instance.id, receiver))) == 1
    assert len(world_engine.get_events(instance.id)) == events_before
    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )


def test_share_does_not_downgrade_observed_knowledge(world_engine: WorldEngine) -> None:
    instance, sharer, receiver = setup_two_at_station(world_engine)
    inspect(world_engine, instance, receiver)
    inspect(world_engine, instance, sharer)
    observed = list(world_engine.get_knowledge(instance.id, receiver))[0]
    assert observed.claim_type is ClaimType.OBSERVATION

    result = share(world_engine, instance, sharer, receiver)

    assert result.ok is True and result.payload["already_known"] is True
    still = list(world_engine.get_knowledge(instance.id, receiver))[0]
    assert still == observed
    assert still.claim_type is ClaimType.OBSERVATION
    assert still.source is KnowledgeSource.OBSERVATION


@pytest.mark.parametrize("claim_type", list(ClaimType))
def test_all_claim_types_are_persisted(
    world_engine: WorldEngine, uow_factory, claim_type: ClaimType
) -> None:
    """Проверяем персистентность всех пяти типов claim, а не семантические пары."""
    instance, sharer, _receiver = setup_two_at_station(world_engine)
    information = world_engine.get_information(instance.id, "damaged_radio")
    knowledge = Knowledge.record(
        id=KnowledgeId(f"kn_{claim_type.value.lower()}"),
        world_instance_id=instance.id,
        subject_type=SubjectType.CHARACTER,
        subject_id=str(sharer),
        information_id=information.id,
        claim=CLAIM,
        claim_type=claim_type,
        source=KnowledgeSource.DOCUMENT,
        source_ref="document_17",
        confidence=KnowledgeConfidence.UNCERTAIN,
        acquired_at=NOW,
    )
    with uow_factory() as uow:
        uow.knowledge.add(knowledge)
        uow.commit()

    with uow_factory() as uow:
        stored = uow.knowledge.find(
            instance.id, SubjectType.CHARACTER, str(sharer), information.id
        )

    assert stored is not None
    assert stored.claim_type is claim_type
    assert stored.source is KnowledgeSource.DOCUMENT
    assert stored.confidence is KnowledgeConfidence.UNCERTAIN
    assert stored.source_ref == "document_17"


def test_share_does_not_touch_information_record(world_engine: WorldEngine) -> None:
    instance, sharer, receiver = setup_two_at_station(world_engine)
    inspect(world_engine, instance, sharer)
    before = world_engine.get_information(instance.id, "damaged_radio")

    assert share(world_engine, instance, sharer, receiver).ok is True

    after = world_engine.get_information(instance.id, "damaged_radio")
    assert after.discovery_state is before.discovery_state
    assert after.discovered_by == before.discovered_by == sharer
    assert after.discovered_at == before.discovered_at
    assert after.location_key == before.location_key
    assert after.key == before.key


def test_share_without_sharer_knowledge_is_invalid_action(world_engine: WorldEngine) -> None:
    instance, sharer, receiver = setup_two_at_station(world_engine)
    events_before = len(world_engine.get_events(instance.id))
    state_before = world_engine.get_instance(instance.id).state

    result = share(world_engine, instance, sharer, receiver)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.INVALID_ACTION
    assert list(world_engine.get_knowledge(instance.id, receiver)) == []
    assert len(world_engine.get_events(instance.id)) == events_before
    assert world_engine.get_instance(instance.id).state.state_version == state_before.state_version


def test_share_with_unknown_information_is_not_found(world_engine: WorldEngine) -> None:
    instance, sharer, receiver = setup_two_at_station(world_engine)
    inspect(world_engine, instance, sharer)
    events_before = len(world_engine.get_events(instance.id))

    result = share(world_engine, instance, sharer, receiver, information_key="unknown_clue")

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_FOUND
    assert list(world_engine.get_knowledge(instance.id, receiver)) == []
    assert len(world_engine.get_events(instance.id)) == events_before


def test_share_across_instances_leaves_no_trace(world_engine: WorldEngine) -> None:
    instance, sharer, local_receiver = setup_two_at_station(world_engine)
    inspect(world_engine, instance, sharer)

    other_world = make_world(world_engine, chat_id=-1002)
    foreign_character = make_character(world_engine, other_world, "player-foreign")

    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))
    other_state_before = world_engine.get_instance(other_world.id).state
    other_events_before = len(world_engine.get_events(other_world.id))

    result = share(world_engine, instance, sharer, foreign_character)

    # Чужой персонаж не виден в этом мире: NOT_FOUND, а не «поделились не туда».
    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_FOUND

    assert world_engine.get_instance(instance.id).state.state_version == state_before.state_version
    assert world_engine.get_instance(instance.id).state.world_tick == state_before.world_tick
    assert len(world_engine.get_events(instance.id)) == events_before
    assert list(world_engine.get_knowledge(instance.id, local_receiver)) == []
    assert len(list(world_engine.get_knowledge(instance.id, sharer))) == 1  # только наблюдение

    assert (
        world_engine.get_instance(other_world.id).state.state_version
        == other_state_before.state_version
    )
    assert len(world_engine.get_events(other_world.id)) == other_events_before
    assert list(world_engine.get_knowledge(other_world.id, foreign_character)) == []


def test_database_rejects_knowledge_linked_to_foreign_instance_information(
    world_engine: WorldEngine, uow_factory
) -> None:  # noqa: ANN001
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    character_id = make_character(world_engine, world_one, "player-a")
    foreign_information = world_engine.get_information(world_two.id, "damaged_radio")
    record = Knowledge.record(
        id=KnowledgeId("kn_cross_instance"),
        world_instance_id=world_one.id,
        subject_type=SubjectType.CHARACTER,
        subject_id=str(character_id),
        information_id=foreign_information.id,
        claim=CLAIM,
        claim_type=ClaimType.CLAIM,
        source=KnowledgeSource.CHARACTER,
        source_ref=str(character_id),
        confidence=KnowledgeConfidence.LIKELY,
        acquired_at=NOW,
    )

    with pytest.raises(IntegrityError):
        with uow_factory() as uow:
            uow.knowledge.add(record)

    assert world_engine.get_knowledge(world_one.id, character_id) == []


def test_share_across_locations_is_not_allowed(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    sharer = make_character(world_engine, instance, "player-a")
    receiver = make_character(world_engine, instance, "player-b")
    travel_to_station(world_engine, instance, sharer)  # receiver остаётся в base
    inspect(world_engine, instance, sharer)

    events_before = len(world_engine.get_events(instance.id))
    state_before = world_engine.get_instance(instance.id).state

    result = share(world_engine, instance, sharer, receiver)

    assert result.ok is False
    assert result.error is not None
    assert result.error.code is ErrorCode.NOT_ALLOWED
    assert list(world_engine.get_knowledge(instance.id, receiver)) == []
    assert len(world_engine.get_events(instance.id)) == events_before
    assert world_engine.get_instance(instance.id).state.state_version == state_before.state_version
