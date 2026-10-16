"""Integration: действия NPC — события, валидация, влияние на мир."""

from __future__ import annotations

from typing import Callable

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import ClaimType, KnowledgeSource
from world_error.domain.npcs.npc import Npc, NpcStatus
from world_error.domain.shared.kernel import (
    CharacterId,
    DiscoveryState,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
)
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

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
        result = world_engine.move_character(
            instance.id, character_id=character_id, to_location_key=target
        )
        assert result.ok is True, result.error


def test_world_creation_materialises_npcs(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npcs = world_engine.get_npcs(instance.id)

    assert [(npc.key, str(npc.location_key), npc.status.value) for npc in npcs] == [
        ("caretaker", "base", "ACTIVE"),
        ("mechanic", "old_station", "ACTIVE"),
        ("scout", "forest", "ACTIVE"),
    ]
    assert [event.type for event in world_engine.get_events(instance.id)] == [
        EventType.WORLD_INSTANCE_CREATED
    ]
    assert instance.state.state_version == 0


def test_npc_move_changes_location_and_creates_event(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    scout = npc_by_key(world_engine, instance, "scout")
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.npc_move(instance.id, npc_id=scout.id, to_location_key=OLD_STATION)

    assert result.ok is True, result.error
    assert (result.payload["from"], result.payload["to"]) == ("forest", "old_station")
    moved = world_engine.get_npc(instance.id, scout.id)
    assert moved.location_key == OLD_STATION

    events = world_engine.get_events(instance.id)
    assert len(events) == events_before + 1
    assert events[-1].type is EventType.NPC_MOVED
    assert events[-1].actor == str(scout.id)
    assert dict(events[-1].payload) == {"from": "forest", "to": "old_station"}
    state_after = world_engine.get_instance(instance.id).state
    assert state_after.world_tick == state_before.world_tick + 1
    assert state_after.state_version == state_before.state_version + 1


def test_npc_move_to_unconnected_location_is_rejected(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")  # old_station
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.npc_move(instance.id, npc_id=mechanic.id, to_location_key=BASE)

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ACTION
    assert world_engine.get_npc(instance.id, mechanic.id).location_key == OLD_STATION
    assert len(world_engine.get_events(instance.id)) == events_before


def test_missing_npc_cannot_move(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    scout = npc_by_key(world_engine, instance, "scout")
    assert world_engine.npc_change_status(
        instance.id, npc_id=scout.id, to_status=NpcStatus.MISSING
    ).ok is True

    result = world_engine.npc_move(instance.id, npc_id=scout.id, to_location_key=OLD_STATION)

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_ALLOWED


def test_npc_observes_information_and_changes_world(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")

    result = world_engine.npc_observe_information(
        instance.id, npc_id=mechanic.id, information_key=INFO_KEY
    )

    assert result.ok is True, result.error
    information = world_engine.get_information(instance.id, INFO_KEY)
    assert information.discovery_state is DiscoveryState.DISCOVERED
    assert information.discovered_by == str(mechanic.id)

    knowledge = list(world_engine.get_npc_knowledge(instance.id, mechanic.id))
    assert len(knowledge) == 1
    assert knowledge[0].claim_type is ClaimType.OBSERVATION
    assert knowledge[0].source is KnowledgeSource.OBSERVATION
    assert knowledge[0].subject_id == str(mechanic.id)
    assert result.payload["claim_type"] == "OBSERVATION"

    events = world_engine.get_events(instance.id)
    assert events[-1].type is EventType.INFORMATION_DISCOVERED
    assert events[-1].actor == str(mechanic.id)


def test_npc_observe_does_not_overwrite_first_discoverer(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    character = make_character(world_engine, instance)
    travel_to_station(world_engine, instance, character)
    assert world_engine.inspect_information(
        instance.id, character_id=character, target_key=INFO_KEY
    ).ok is True
    mechanic = npc_by_key(world_engine, instance, "mechanic")

    result = world_engine.npc_observe_information(
        instance.id, npc_id=mechanic.id, information_key=INFO_KEY
    )

    assert result.ok is True
    information = world_engine.get_information(instance.id, INFO_KEY)
    assert information.discovered_by == str(character)
    assert result.payload["discovered_by"] == str(character)
    assert len(list(world_engine.get_npc_knowledge(instance.id, mechanic.id))) == 1
    assert len(list(world_engine.get_knowledge(instance.id, character))) == 1


def test_repeated_npc_observe_is_noop(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")
    assert world_engine.npc_observe_information(
        instance.id, npc_id=mechanic.id, information_key=INFO_KEY
    ).ok is True

    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    second = world_engine.npc_observe_information(
        instance.id, npc_id=mechanic.id, information_key=INFO_KEY
    )

    assert second.ok is True and second.payload["already_known"] is True
    assert second.payload["claim_type"] == "OBSERVATION"
    assert second.event_ids == ()
    assert len(world_engine.get_events(instance.id)) == events_before
    assert len(list(world_engine.get_npc_knowledge(instance.id, mechanic.id))) == 1
    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )


def test_npc_learn_uses_content_by_default(world_engine: WorldEngine, catalog) -> None:
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")
    definition = catalog.information_definition(INFO_KEY)

    result = world_engine.npc_learn(instance.id, npc_id=mechanic.id, information_key=INFO_KEY)

    assert result.ok is True, result.error
    assert result.payload["claim"] == definition.content
    assert result.payload["claim"] != definition.truth
    knowledge = list(world_engine.get_npc_knowledge(instance.id, mechanic.id))
    assert knowledge[0].claim == definition.content
    assert knowledge[0].claim_type is ClaimType.FACT
    event = world_engine.get_events(instance.id)[-1]
    assert event.type is EventType.NPC_LEARNED
    assert event.payload["claim"] == definition.content


def test_npc_can_hold_false_belief(world_engine: WorldEngine, catalog) -> None:
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")
    definition = catalog.information_definition(INFO_KEY)
    wrong_claim = "Радио сломала гроза."

    result = world_engine.npc_learn(
        instance.id,
        npc_id=mechanic.id,
        information_key=INFO_KEY,
        claim_type=ClaimType.THEORY,
        source=KnowledgeSource.HYPOTHESIS,
        claim=wrong_claim,
    )

    assert result.ok is True
    knowledge = list(world_engine.get_npc_knowledge(instance.id, mechanic.id))[0]
    assert knowledge.claim == wrong_claim
    assert knowledge.claim != definition.content
    assert knowledge.claim != definition.truth
    assert knowledge.claim_type is ClaimType.THEORY
    event = world_engine.get_events(instance.id)[-1]
    assert event.type is EventType.NPC_LEARNED
    assert event.payload["claim"] == wrong_claim


def test_repeated_npc_learn_is_noop(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")
    assert world_engine.npc_learn(
        instance.id, npc_id=mechanic.id, information_key=INFO_KEY
    ).ok is True
    events_before = len(world_engine.get_events(instance.id))

    second = world_engine.npc_learn(instance.id, npc_id=mechanic.id, information_key=INFO_KEY)

    assert second.ok is True and second.payload["already_known"] is True
    assert second.event_ids == ()
    assert len(world_engine.get_events(instance.id)) == events_before
    assert len(list(world_engine.get_npc_knowledge(instance.id, mechanic.id))) == 1


def test_npc_status_change_creates_event(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_by_key(world_engine, instance, "caretaker")

    gone = world_engine.npc_change_status(
        instance.id, npc_id=caretaker.id, to_status=NpcStatus.MISSING
    )
    assert gone.ok is True
    assert gone.payload["to"] == "MISSING"
    assert world_engine.get_npc(instance.id, caretaker.id).status is NpcStatus.MISSING

    back = world_engine.npc_change_status(
        instance.id, npc_id=caretaker.id, to_status=NpcStatus.ACTIVE
    )
    assert back.ok is True
    assert back.payload["from"] == "MISSING"
    assert world_engine.get_npc(instance.id, caretaker.id).status is NpcStatus.ACTIVE

    events = [event.type for event in world_engine.get_events(instance.id)]
    assert events.count(EventType.NPC_STATUS_CHANGED) == 2


def test_status_change_to_same_status_is_noop(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_by_key(world_engine, instance, "caretaker")
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.npc_change_status(
        instance.id, npc_id=caretaker.id, to_status=NpcStatus.ACTIVE
    )

    assert result.ok is True and result.payload["changed"] is False
    assert result.event_ids == ()
    assert len(world_engine.get_events(instance.id)) == events_before


def test_npc_acts_without_any_player_in_the_world(world_engine: WorldEngine) -> None:
    """NPC не ждут игрока (05_NPCS §6): в мире нет ни одного персонажа."""
    instance = make_world(world_engine)
    scout = npc_by_key(world_engine, instance, "scout")
    mechanic = npc_by_key(world_engine, instance, "mechanic")

    moved = world_engine.npc_move(instance.id, npc_id=scout.id, to_location_key=OLD_STATION)
    observed = world_engine.npc_observe_information(
        instance.id, npc_id=mechanic.id, information_key=INFO_KEY
    )

    assert moved.ok is True and observed.ok is True
    event_types = [event.type for event in world_engine.get_events(instance.id)]
    assert EventType.CHARACTER_CREATED not in event_types
    assert EventType.NPC_MOVED in event_types
    assert EventType.INFORMATION_DISCOVERED in event_types


def test_each_npc_action_creates_exactly_one_event(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    scout = npc_by_key(world_engine, instance, "scout")
    mechanic = npc_by_key(world_engine, instance, "mechanic")

    actions = (
        lambda: world_engine.npc_move(instance.id, npc_id=scout.id, to_location_key=OLD_STATION),
        lambda: world_engine.npc_observe_information(
            instance.id, npc_id=mechanic.id, information_key=INFO_KEY
        ),
        lambda: world_engine.npc_learn(
            instance.id, npc_id=scout.id, information_key=INFO_KEY
        ),
        lambda: world_engine.npc_change_status(
            instance.id, npc_id=scout.id, to_status=NpcStatus.MISSING
        ),
    )

    for action in actions:
        events_before = len(world_engine.get_events(instance.id))
        state_before = world_engine.get_instance(instance.id).state

        result = action()
        assert result.ok is True, result.error
        assert len(result.event_ids) == 1

        events = world_engine.get_events(instance.id)
        assert len(events) == events_before + 1
        assert str(events[-1].actor).startswith("npc_")
        state_after = world_engine.get_instance(instance.id).state
        assert state_after.state_version == state_before.state_version + 1
        assert state_after.world_tick == state_before.world_tick + 1


def test_duplicate_npc_event_is_rejected(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = make_world(world_engine)
    scout = npc_by_key(world_engine, instance, "scout")
    assert world_engine.npc_move(
        instance.id, npc_id=scout.id, to_location_key=OLD_STATION
    ).ok is True
    move_event = next(
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.NPC_MOVED
    )
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    with uow_factory() as uow:
        npc = uow.npcs.get(instance.id, scout.id)
        npc.location_key = FOREST  # имитируем переход состояния
        with pytest.raises(DomainError) as exc_info:
            uow.events.append(move_event)
        assert exc_info.value.code is ErrorCode.ALREADY_PROCESSED
        uow.rollback()

    assert world_engine.get_npc(instance.id, scout.id).location_key == OLD_STATION
    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )
    assert len(world_engine.get_events(instance.id)) == events_before
