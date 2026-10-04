"""Integration: отношения — команды, асимметрия, изоляция, гейт знаний."""

from __future__ import annotations

from typing import Callable

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import (
    RelationshipDirection,
    RelationshipKind,
    SubjectRef,
    SuspicionLevel,
    TrustLevel,
)
from world_error.domain.relationships.rules import SignificantAction
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    LocationKey,
)
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")
INFO_KEY = "damaged_radio"


def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def npc_by_key(world_engine: WorldEngine, instance: WorldInstance, key: str) -> SubjectRef:
    npc = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == key)
    return SubjectRef(type=SubjectType.NPC, id=str(npc.id))


def npc_id_by_key(world_engine: WorldEngine, instance: WorldInstance, key: str):
    return next(npc.id for npc in world_engine.get_npcs(instance.id) if npc.key == key)


def make_character(
    world_engine: WorldEngine, instance: WorldInstance, player_id: str = "player-a"
) -> SubjectRef:
    result = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert result.ok is True, result.error
    return SubjectRef(type=SubjectType.CHARACTER, id=result.payload["character_id"])


def level_of(
    world_engine: WorldEngine,
    instance: WorldInstance,
    holder: SubjectRef,
    subject: SubjectRef,
    kind: RelationshipKind,
):
    relationship = world_engine.get_relationship(
        instance.id, holder=holder, subject=subject, kind=kind
    )
    return None if relationship is None else relationship.level


def test_change_relationship_creates_record_and_event(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.change_relationship(
        instance.id,
        holder=npc,
        subject=character,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
        reason="manual",
    )

    assert result.ok is True, result.error
    assert result.payload["changed"] is True
    assert (result.payload["from"], result.payload["to"]) == ("NEUTRAL", "FRIENDLY")
    assert level_of(world_engine, instance, npc, character, RelationshipKind.TRUST) is TrustLevel.FRIENDLY

    events = world_engine.get_events(instance.id)
    assert len(events) == events_before + 1
    event = events[-1]
    assert event.type is EventType.RELATIONSHIP_CHANGED
    assert event.actor == npc.id
    assert event.target == character.id
    assert event.payload["holder_id"] == npc.id
    assert event.payload["subject_id"] == character.id
    assert event.payload["changes"] == [
        {"kind": "TRUST", "from": "NEUTRAL", "to": "FRIENDLY"}
    ]
    state_after = world_engine.get_instance(instance.id).state
    assert state_after.world_tick == state_before.world_tick + 1
    assert state_after.state_version == state_before.state_version + 1


def test_relationship_is_asymmetric(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)

    assert world_engine.change_relationship(
        instance.id,
        holder=npc,
        subject=character,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    ).ok is True

    # Обратного отношения никто не создавал.
    assert world_engine.get_relationship(
        instance.id, holder=character, subject=npc, kind=RelationshipKind.TRUST
    ) is None
    assert world_engine.list_relationships_of(instance.id, character) == []

    # Обратное изменение не трогает прямое.
    assert world_engine.change_relationship(
        instance.id,
        holder=character,
        subject=npc,
        kind=RelationshipKind.SUSPICION,
        direction=RelationshipDirection.INCREASE,
    ).ok is True

    assert level_of(world_engine, instance, npc, character, RelationshipKind.TRUST) is TrustLevel.FRIENDLY
    assert level_of(world_engine, instance, character, npc, RelationshipKind.SUSPICION) is SuspicionLevel.LOW


def test_change_at_ladder_edge_is_noop_without_event(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)
    events_before = len(world_engine.get_events(instance.id))

    # SUSPICION стартует с NONE: понижать некуда.
    result = world_engine.change_relationship(
        instance.id,
        holder=npc,
        subject=character,
        kind=RelationshipKind.SUSPICION,
        direction=RelationshipDirection.DECREASE,
    )

    assert result.ok is True
    assert result.payload["changed"] is False
    assert result.event_ids == ()
    assert len(world_engine.get_events(instance.id)) == events_before
    assert world_engine.get_relationship(
        instance.id, holder=npc, subject=character, kind=RelationshipKind.SUSPICION
    ) is None


def test_significant_action_betrayed_moves_two_kinds(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.apply_significant_action(
        instance.id, actor=character, holder=npc, action=SignificantAction.BETRAYED
    )

    assert result.ok is True, result.error
    assert result.payload["changed"] is True
    changes = {change["kind"]: (change["from"], change["to"]) for change in result.payload["changes"]}
    assert changes["TRUST"] == ("NEUTRAL", "WARY")
    assert changes["SUSPICION"] == ("NONE", "LOW")
    assert level_of(world_engine, instance, npc, character, RelationshipKind.TRUST) is TrustLevel.WARY
    assert level_of(world_engine, instance, npc, character, RelationshipKind.SUSPICION) is SuspicionLevel.LOW

    # Одно действие — одно событие, несмотря на два изменения.
    assert len(world_engine.get_events(instance.id)) == events_before + 1
    event = world_engine.get_events(instance.id)[-1]
    assert event.type is EventType.RELATIONSHIP_CHANGED
    assert event.actor == character.id
    assert event.target == npc.id
    assert event.payload["reason"] == "BETRAYED"


def test_significant_action_helped_raises_trust_only(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)

    result = world_engine.apply_significant_action(
        instance.id, actor=character, holder=npc, action=SignificantAction.HELPED
    )

    assert result.ok is True
    assert result.payload["changes"] == [
        {"kind": "TRUST", "from": "NEUTRAL", "to": "FRIENDLY"}
    ]
    assert level_of(world_engine, instance, npc, character, RelationshipKind.TRUST) is TrustLevel.FRIENDLY
    assert world_engine.get_relationship(
        instance.id, holder=npc, subject=character, kind=RelationshipKind.SUSPICION
    ) is None


def test_significant_action_between_two_npcs(world_engine: WorldEngine) -> None:
    """NPC помнит действие другого NPC так же, как действие игрока (M7)."""
    instance = make_world(world_engine)
    mechanic = npc_by_key(world_engine, instance, "mechanic")
    scout = npc_by_key(world_engine, instance, "scout")

    result = world_engine.apply_significant_action(
        instance.id, actor=scout, holder=mechanic, action=SignificantAction.BETRAYED
    )

    assert result.ok is True, result.error
    assert level_of(world_engine, instance, mechanic, scout, RelationshipKind.TRUST) is TrustLevel.WARY
    assert level_of(world_engine, instance, mechanic, scout, RelationshipKind.SUSPICION) is SuspicionLevel.LOW
    # Обратного отношения нет: асимметрия сохраняется и между NPC.
    assert world_engine.get_relationship(
        instance.id, holder=scout, subject=mechanic, kind=RelationshipKind.TRUST
    ) is None


def test_relationship_change_to_self_is_rejected(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.change_relationship(
        instance.id,
        holder=npc,
        subject=npc,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ACTION
    assert len(world_engine.get_events(instance.id)) == events_before


def test_faction_subject_is_rejected_by_domain(world_engine: WorldEngine) -> None:
    """M1: FACTION отклоняется до Phase 18."""
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    faction = SubjectRef(type=SubjectType.FACTION, id="faction_1")
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.change_relationship(
        instance.id,
        holder=npc,
        subject=faction,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ACTION
    assert world_engine.list_relationships_of(instance.id, npc) == []
    assert len(world_engine.get_events(instance.id)) == events_before


def test_cross_instance_subject_leaves_no_trace(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    npc_one = npc_by_key(world_engine, world_one, "mechanic")
    foreign = make_character(world_engine, world_two, "player-b")

    state_before = world_engine.get_instance(world_one.id).state
    events_before = len(world_engine.get_events(world_one.id))
    other_events_before = len(world_engine.get_events(world_two.id))

    result = world_engine.change_relationship(
        world_one.id,
        holder=npc_one,
        subject=foreign,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_FOUND
    assert world_engine.list_relationships_of(world_one.id, npc_one) == []
    assert len(world_engine.get_events(world_one.id)) == events_before
    assert world_engine.get_instance(world_one.id).state.state_version == state_before.state_version
    assert len(world_engine.get_events(world_two.id)) == other_events_before
    assert world_engine.list_relationships_about(world_two.id, foreign) == []


def test_duplicate_relationship_event_is_rejected(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)
    assert world_engine.change_relationship(
        instance.id,
        holder=npc,
        subject=character,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    ).ok is True

    event = next(
        item
        for item in world_engine.get_events(instance.id)
        if item.type is EventType.RELATIONSHIP_CHANGED
    )
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    with uow_factory() as uow:
        with pytest.raises(DomainError) as exc_info:
            uow.events.append(event)
        assert exc_info.value.code is ErrorCode.ALREADY_PROCESSED
        uow.rollback()

    assert level_of(world_engine, instance, npc, character, RelationshipKind.TRUST) is TrustLevel.FRIENDLY
    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )
    assert len(world_engine.get_events(instance.id)) == events_before


def test_each_relationship_action_creates_exactly_one_event(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)
    scout = npc_by_key(world_engine, instance, "scout")

    actions = (
        lambda: world_engine.change_relationship(
            instance.id,
            holder=npc,
            subject=character,
            kind=RelationshipKind.TRUST,
            direction=RelationshipDirection.INCREASE,
        ),
        lambda: world_engine.apply_significant_action(
            instance.id, actor=character, holder=npc, action=SignificantAction.LIED_TO
        ),
        lambda: world_engine.apply_significant_action(
            instance.id, actor=scout, holder=npc, action=SignificantAction.HELPED
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
        assert events[-1].type is EventType.RELATIONSHIP_CHANGED
        state_after = world_engine.get_instance(instance.id).state
        assert state_after.state_version == state_before.state_version + 1
        assert state_after.world_tick == state_before.world_tick + 1


def test_relationship_survives_movement_and_observation(world_engine: WorldEngine) -> None:
    """NPC помнит значимое действие: обычные действия отношение не сбрасывают."""
    instance = make_world(world_engine)
    npc_ref = npc_by_key(world_engine, instance, "mechanic")
    npc_id = npc_id_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)
    assert world_engine.apply_significant_action(
        instance.id, actor=character, holder=npc_ref, action=SignificantAction.BETRAYED
    ).ok is True

    assert world_engine.npc_move(
        instance.id, npc_id=npc_id, to_location_key=FOREST
    ).ok is True
    assert world_engine.npc_observe_information(
        instance.id, npc_id=npc_id, information_key=INFO_KEY
    ).ok is False  # damaged_radio в old_station, NPC теперь в лесу

    assert level_of(world_engine, instance, npc_ref, character, RelationshipKind.TRUST) is TrustLevel.WARY
    assert level_of(
        world_engine, instance, npc_ref, character, RelationshipKind.SUSPICION
    ) is SuspicionLevel.LOW


# --- гейт: NPC не учится у того, кому не доверяет --------------------------


def test_neutral_relationship_allows_learning(world_engine: WorldEngine) -> None:
    """M2: базовая ступень NEUTRAL/NONE пропускает знание — старые тесты 4 целы."""
    instance = make_world(world_engine)
    npc_id = npc_id_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)

    result = world_engine.npc_learn(
        instance.id, npc_id=npc_id, information_key=INFO_KEY, source_ref=character.id
    )

    assert result.ok is True, result.error
    assert len(list(world_engine.get_npc_knowledge(instance.id, npc_id))) == 1


def test_gate_blocks_learning_from_distrusted_source(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    npc_id = npc_id_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)

    # NEUTRAL -> WARY -> HOSTILE
    for _ in range(2):
        assert world_engine.change_relationship(
            instance.id,
            holder=npc,
            subject=character,
            kind=RelationshipKind.TRUST,
            direction=RelationshipDirection.DECREASE,
        ).ok is True
    assert level_of(world_engine, instance, npc, character, RelationshipKind.TRUST) is TrustLevel.HOSTILE

    events_before = len(world_engine.get_events(instance.id))
    result = world_engine.npc_learn(
        instance.id, npc_id=npc_id, information_key=INFO_KEY, source_ref=character.id
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_ALLOWED
    assert list(world_engine.get_npc_knowledge(instance.id, npc_id)) == []
    assert len(world_engine.get_events(instance.id)) == events_before


def test_gate_blocks_learning_when_suspicion_is_high(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    npc_id = npc_id_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)

    # NONE -> LOW -> MEDIUM -> HIGH
    for _ in range(3):
        assert world_engine.change_relationship(
            instance.id,
            holder=npc,
            subject=character,
            kind=RelationshipKind.SUSPICION,
            direction=RelationshipDirection.INCREASE,
        ).ok is True

    result = world_engine.npc_learn(
        instance.id, npc_id=npc_id, information_key=INFO_KEY, source_ref=character.id
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_ALLOWED
    assert list(world_engine.get_npc_knowledge(instance.id, npc_id)) == []


def test_gate_ignores_non_subject_source_reference(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc_id = npc_id_by_key(world_engine, instance, "mechanic")

    result = world_engine.npc_learn(
        instance.id, npc_id=npc_id, information_key=INFO_KEY, source_ref="document_17"
    )

    assert result.ok is True, result.error


def test_gate_does_not_block_repeat_learning(world_engine: WorldEngine) -> None:
    """Повторное обучение остаётся no-op даже если отношение испортилось позже."""
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    npc_id = npc_id_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)

    assert world_engine.npc_learn(
        instance.id, npc_id=npc_id, information_key=INFO_KEY, source_ref=character.id
    ).ok is True
    for _ in range(2):
        assert world_engine.change_relationship(
            instance.id,
            holder=npc,
            subject=character,
            kind=RelationshipKind.TRUST,
            direction=RelationshipDirection.DECREASE,
        ).ok is True

    events_before = len(world_engine.get_events(instance.id))
    repeat = world_engine.npc_learn(
        instance.id, npc_id=npc_id, information_key=INFO_KEY, source_ref=character.id
    )

    assert repeat.ok is True and repeat.payload["already_known"] is True
    assert len(world_engine.get_events(instance.id)) == events_before
    assert len(list(world_engine.get_npc_knowledge(instance.id, npc_id))) == 1


def test_character_id_type_is_used_for_foreign_lookup(world_engine: WorldEngine) -> None:
    """Страховка: id персонажа из другого мира действительно не находится."""
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    foreign = make_character(world_engine, world_two, "player-b")

    with pytest.raises(DomainError) as exc_info:
        world_engine.get_character(world_one.id, CharacterId(foreign.id))
    assert exc_info.value.code is ErrorCode.NOT_FOUND
