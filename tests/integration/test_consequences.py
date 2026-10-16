"""Integration: последствия — немедленные, отложенные, косвенные, каскад, правила."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.consequences.consequence import ConsequenceTrigger
from world_error.domain.consequences.vocabulary import (
    CauseOrigin,
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceStatus,
    ConsequenceType,
    ConsequenceVisibility,
)
from world_error.domain.events.event import Event, EventType
from world_error.domain.knowledge.knowledge import ClaimType, KnowledgeSource
from world_error.domain.relationships.relationship import (
    RelationshipKind,
    SubjectRef,
    TrustLevel,
)
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    CharacterId,
    ConsequenceId,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    NpcId,
)
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.content.loader import load_content_catalog
from world_error.infrastructure.db.engine import create_session_factory
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

INFO_KEY = "damaged_radio"
FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")


# --- helpers ---------------------------------------------------------------


def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def npc_id_by_key(world_engine: WorldEngine, instance: WorldInstance, key: str) -> NpcId:
    return next(npc.id for npc in world_engine.get_npcs(instance.id) if npc.key == key)


def make_character(
    world_engine: WorldEngine, instance: WorldInstance, player_id: str = "player-a"
) -> CharacterId:
    result = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert result.ok is True, result.error
    return CharacterId(result.payload["character_id"])


def last_event(world_engine: WorldEngine, instance: WorldInstance) -> Event:
    return world_engine.get_events(instance.id)[-1]


def events_of_type(
    world_engine: WorldEngine, instance: WorldInstance, event_type: EventType
) -> list[Event]:
    return [event for event in world_engine.get_events(instance.id) if event.type is event_type]


def schedule(
    world_engine: WorldEngine,
    instance: WorldInstance,
    *,
    cause_event_ids: tuple[EventId, ...],
    effect: ConsequenceEffect = ConsequenceEffect.INFORMATIONAL_LEARN,
    type: ConsequenceType = ConsequenceType.INFORMATIONAL,
    trigger: ConsequenceTrigger | None = None,
    payload: dict[str, Any],
    scale: ConsequenceScale = ConsequenceScale.LOCAL,
    visibility: ConsequenceVisibility = ConsequenceVisibility.HIDDEN,
    rule_key: str | None = None,
):
    return world_engine.schedule_consequence(
        instance.id,
        cause_event_ids=cause_event_ids,
        type=type,
        scale=scale,
        visibility=visibility,
        trigger=trigger or ConsequenceTrigger.immediate(),
        effect=effect,
        payload=payload,
        rule_key=rule_key,
    )


def informational_payload(npc_id: NpcId, information_key: str = INFO_KEY) -> dict[str, Any]:
    return {"npc_id": str(npc_id), "information_key": information_key}


# --- 1. прямое последствие -------------------------------------------------


def test_immediate_consequence_applies_at_once(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    cause = last_event(world_engine, instance).id

    result = schedule(
        world_engine, instance, cause_event_ids=(cause,), payload=informational_payload(caretaker)
    )

    assert result.ok is True, result.error
    assert result.payload["status"] == ConsequenceStatus.PENDING.value
    assert result.payload["consequences_applied"] == 1
    consequence = world_engine.get_consequence(instance.id, ConsequenceId(result.payload["consequence_id"]))
    assert consequence.status is ConsequenceStatus.APPLIED
    assert consequence.applied_event_id is not None
    applied_event = next(
        event
        for event in world_engine.get_events(instance.id)
        if event.id == consequence.applied_event_id
    )
    assert applied_event.type is EventType.NPC_LEARNED

    knowledge = list(world_engine.get_npc_knowledge(instance.id, caretaker))
    assert len(knowledge) == 1
    assert applied_event.payload["claim"] == knowledge[0].claim
    confirmed = events_of_type(world_engine, instance, EventType.NPC_LEARNED)
    assert len(confirmed) == 1
    assert confirmed[0].cause == f"consequence:{consequence.id}"
    assert confirmed[0].payload["information_key"] == INFO_KEY


# --- 2. отложенное последствие ---------------------------------------------


def test_delayed_consequence_waits_for_ticks(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    mechanic = npc_id_by_key(world_engine, instance, "mechanic")
    cause = last_event(world_engine, instance).id

    result = schedule(
        world_engine,
        instance,
        cause_event_ids=(cause,),
        trigger=ConsequenceTrigger.after_ticks(3),
        payload=informational_payload(mechanic),
    )
    assert result.ok is True, result.error
    due_tick = int(result.payload["due_tick"])
    assert result.payload.get("consequences_applied", 0) == 0

    # До срока мир не меняется вообще.
    assert list(world_engine.get_npc_knowledge(instance.id, mechanic)) == []
    while world_engine.get_instance(instance.id).state.world_tick < due_tick - 1:
        world_engine.advance_tick(instance.id)
    assert list(world_engine.get_npc_knowledge(instance.id, mechanic)) == []

    world_engine.advance_tick(instance.id)
    assert world_engine.get_instance(instance.id).state.world_tick >= due_tick
    assert len(list(world_engine.get_npc_knowledge(instance.id, mechanic))) == 1


def test_delayed_consequence_applies_once(world_engine: WorldEngine) -> None:
    """M3: отложенное последствие не запускается своим же эффектом."""
    instance = make_world(world_engine)
    mechanic = npc_id_by_key(world_engine, instance, "mechanic")
    cause = last_event(world_engine, instance).id
    result = schedule(
        world_engine,
        instance,
        cause_event_ids=(cause,),
        trigger=ConsequenceTrigger.after_ticks(1),
        payload=informational_payload(mechanic),
    )
    due_tick = int(result.payload["due_tick"])
    while world_engine.get_instance(instance.id).state.world_tick < due_tick:
        world_engine.advance_tick(instance.id)

    for _ in range(3):
        world_engine.pump_consequences(instance.id)

    assert len(events_of_type(world_engine, instance, EventType.NPC_LEARNED)) == 1
    assert len(list(world_engine.get_npc_knowledge(instance.id, mechanic))) == 1


# --- 3-5. косвенные, цепочка, ветвление ------------------------------------


def test_indirect_consequence_uses_effect_event_as_cause(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    scout = npc_id_by_key(world_engine, instance, "scout")
    cause = last_event(world_engine, instance).id

    first = schedule(
        world_engine, instance, cause_event_ids=(cause,), payload=informational_payload(caretaker)
    )
    assert first.ok is True
    effect_event = events_of_type(world_engine, instance, EventType.NPC_LEARNED)[0]

    second = schedule(
        world_engine,
        instance,
        cause_event_ids=(effect_event.id,),
        effect=ConsequenceEffect.RELATIONAL_SHIFT,
        type=ConsequenceType.RELATIONAL,
        payload={
            "holder_type": "NPC",
            "holder_id": str(caretaker),
            "subject_type": "NPC",
            "subject_id": str(scout),
            "kind": "TRUST",
            "direction": "INCREASE",
        },
    )
    assert second.ok is True, second.error
    second_consequence = world_engine.get_consequence(
        instance.id, ConsequenceId(second.payload["consequence_id"])
    )
    # Косвенность: причина — не действие игрока, а последствие (M10).
    assert second_consequence.causes[0].origin is CauseOrigin.CONSEQUENCE
    relationship = world_engine.get_relationship(
        instance.id,
        holder=SubjectRef(type=SubjectType.NPC, id=str(caretaker)),
        subject=SubjectRef(type=SubjectType.NPC, id=str(scout)),
        kind=RelationshipKind.TRUST,
    )
    assert relationship is not None and relationship.level is TrustLevel.FRIENDLY


def test_chain_of_four_consequences_fires_in_order(world_engine: WorldEngine) -> None:
    """A → B → C → D: каждое следующее ждёт событие предыдущего (ON_EVENT_TYPE)."""
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    mechanic = npc_id_by_key(world_engine, instance, "mechanic")
    scout = npc_id_by_key(world_engine, instance, "scout")
    cause = last_event(world_engine, instance).id

    # B, C, D планируются заранее и ждут событий своих типов.
    chain = (
        ConsequenceTrigger.on_event_type(EventType.NPC_LEARNED),
        ConsequenceTrigger.on_event_type(EventType.RELATIONSHIP_CHANGED),
        ConsequenceTrigger.on_event_type(EventType.NPC_STATUS_CHANGED),
    )
    b = schedule(
        world_engine,
        instance,
        cause_event_ids=(cause,),
        effect=ConsequenceEffect.RELATIONAL_SHIFT,
        type=ConsequenceType.RELATIONAL,
        trigger=chain[0],
        payload={
            "holder_type": "NPC",
            "holder_id": str(mechanic),
            "subject_type": "NPC",
            "subject_id": str(scout),
            "kind": "TRUST",
            "direction": "INCREASE",
        },
    )
    c = schedule(
        world_engine,
        instance,
        cause_event_ids=(cause,),
        effect=ConsequenceEffect.PHYSICAL_STATUS_CHANGE,
        type=ConsequenceType.PHYSICAL,
        trigger=chain[1],
        payload={"npc_id": str(scout), "status": "MISSING"},
    )
    d = schedule(
        world_engine,
        instance,
        cause_event_ids=(cause,),
        effect=ConsequenceEffect.PHYSICAL_RELOCATE,
        type=ConsequenceType.PHYSICAL,
        trigger=chain[2],
        payload={"npc_id": str(mechanic), "to_location_key": "forest"},
    )
    assert b.ok and c.ok and d.ok
    assert b.payload.get("consequences_applied", 0) == 0
    assert list(world_engine.get_npc_knowledge(instance.id, caretaker)) == []

    # A: последствие, эффект которого запускает всю цепочку.
    a = schedule(
        world_engine, instance, cause_event_ids=(cause,), payload=informational_payload(caretaker)
    )

    assert a.ok is True, a.error
    assert a.payload["consequences_applied"] == 4  # A, B, C, D в одном проходе насоса
    statuses = {
        consequence.id: consequence.status
        for consequence in world_engine.list_consequences(instance.id)
    }
    assert set(statuses.values()) == {ConsequenceStatus.APPLIED}
    assert len(list(world_engine.get_npc_knowledge(instance.id, caretaker))) == 1
    assert world_engine.get_npc(instance.id, scout).status.value == "MISSING"
    assert world_engine.get_npc(instance.id, mechanic).location_key == FOREST
    assert [
        event.type
        for event in world_engine.get_events(instance.id)
        if event.type
        in (
            EventType.NPC_LEARNED,
            EventType.RELATIONSHIP_CHANGED,
            EventType.NPC_STATUS_CHANGED,
            EventType.NPC_MOVED,
        )
    ] == [
        EventType.NPC_LEARNED,
        EventType.RELATIONSHIP_CHANGED,
        EventType.NPC_STATUS_CHANGED,
        EventType.NPC_MOVED,
    ]


def test_consequence_graph_branches(world_engine: WorldEngine) -> None:
    """A → B, C; B → D; C → E (§25)."""
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    mechanic = npc_id_by_key(world_engine, instance, "mechanic")
    scout = npc_id_by_key(world_engine, instance, "scout")
    cause = last_event(world_engine, instance).id

    b = schedule(
        world_engine, instance, cause_event_ids=(cause,), payload=informational_payload(caretaker)
    )
    c = schedule(
        world_engine, instance, cause_event_ids=(cause,), payload=informational_payload(mechanic)
    )
    assert b.ok and c.ok
    b_event = [
        event
        for event in events_of_type(world_engine, instance, EventType.NPC_LEARNED)
        if event.actor == str(caretaker)
    ][0]
    c_event = [
        event
        for event in events_of_type(world_engine, instance, EventType.NPC_LEARNED)
        if event.actor == str(mechanic)
    ][0]

    d = schedule(
        world_engine,
        instance,
        cause_event_ids=(b_event.id,),
        effect=ConsequenceEffect.PHYSICAL_STATUS_CHANGE,
        type=ConsequenceType.PHYSICAL,
        payload={"npc_id": str(scout), "status": "MISSING"},
    )
    e = schedule(
        world_engine,
        instance,
        cause_event_ids=(c_event.id,),
        effect=ConsequenceEffect.PHYSICAL_RELOCATE,
        type=ConsequenceType.PHYSICAL,
        payload={"npc_id": str(caretaker), "to_location_key": "forest"},
    )
    assert d.ok and e.ok

    branched = world_engine.list_consequences_caused_by(instance.id, cause)
    assert {consequence.id for consequence in branched} == {
        ConsequenceId(b.payload["consequence_id"]),
        ConsequenceId(c.payload["consequence_id"]),
    }
    from_b = world_engine.list_consequences_caused_by_consequence(
        instance.id, ConsequenceId(b.payload["consequence_id"])
    )
    from_c = world_engine.list_consequences_caused_by_consequence(
        instance.id, ConsequenceId(c.payload["consequence_id"])
    )
    assert {consequence.id for consequence in from_b} == {
        ConsequenceId(d.payload["consequence_id"])
    }
    assert {consequence.id for consequence in from_c} == {
        ConsequenceId(e.payload["consequence_id"])
    }


# --- 6. несколько причин ---------------------------------------------------


def test_multiple_causes(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    make_character(world_engine, instance)
    created_event = [
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.CHARACTER_CREATED
    ][0]

    world_engine.advance_tick(instance.id)
    tick_event = events_of_type(world_engine, instance, EventType.WORLD_TICK_ADVANCED)[-1]

    result = schedule(
        world_engine,
        instance,
        cause_event_ids=(created_event.id, tick_event.id),
        payload=informational_payload(caretaker),
    )

    assert result.ok is True, result.error
    consequence = world_engine.get_consequence(
        instance.id, ConsequenceId(result.payload["consequence_id"])
    )
    assert len(consequence.causes) == 2
    assert {cause.origin for cause in consequence.causes} == {
        CauseOrigin.ACTOR,
        CauseOrigin.WORLD,
    }
    assert consequence.source_event_id == created_event.id
    for cause_event in (created_event, tick_event):
        assert {item.id for item in world_engine.list_consequences_caused_by(instance.id, cause_event.id)} == {
            consequence.id
        }


# --- 9. масштабы и видимость -----------------------------------------------


@pytest.mark.parametrize(
    "scale",
    [
        ConsequenceScale.PERSONAL,
        ConsequenceScale.LOCAL,
        ConsequenceScale.REGIONAL,
        ConsequenceScale.GLOBAL,
    ],
)
def test_scale_is_kept(world_engine: WorldEngine, scale: ConsequenceScale) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    result = schedule(
        world_engine,
        instance,
        cause_event_ids=(last_event(world_engine, instance).id,),
        payload=informational_payload(caretaker),
        scale=scale,
    )
    assert result.payload["scale"] == scale.value
    consequence = world_engine.get_consequence(
        instance.id, ConsequenceId(result.payload["consequence_id"])
    )
    assert consequence.scale is scale


@pytest.mark.parametrize(
    "visibility",
    [
        ConsequenceVisibility.VISIBLE,
        ConsequenceVisibility.PARTIALLY_VISIBLE,
        ConsequenceVisibility.HIDDEN,
        ConsequenceVisibility.INDIRECT,
        ConsequenceVisibility.UNKNOWN,
    ],
)
def test_visibility_does_not_change_behaviour(
    world_engine: WorldEngine, visibility: ConsequenceVisibility
) -> None:
    """§29: видимость — классификация; в коммите 6 поведение не ветвится."""
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    result = schedule(
        world_engine,
        instance,
        cause_event_ids=(last_event(world_engine, instance).id,),
        payload=informational_payload(caretaker),
        visibility=visibility,
    )
    assert result.ok is True
    assert result.payload["consequences_applied"] == 1
    assert len(list(world_engine.get_npc_knowledge(instance.id, caretaker))) == 1


# --- 10. последствие не наказание ------------------------------------------


def test_positive_and_negative_consequences_work_alike(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    scout = npc_id_by_key(world_engine, instance, "scout")
    cause = last_event(world_engine, instance).id

    def shift(direction: str):
        return schedule(
            world_engine,
            instance,
            cause_event_ids=(cause,),
            effect=ConsequenceEffect.RELATIONAL_SHIFT,
            type=ConsequenceType.RELATIONAL,
            payload={
                "holder_type": "NPC",
                "holder_id": str(caretaker),
                "subject_type": "NPC",
                "subject_id": str(scout),
                "kind": "TRUST",
                "direction": direction,
            },
        )

    negative = shift("DECREASE")
    assert negative.ok is True, negative.error
    assert negative.payload["consequences_applied"] == 1

    positive = shift("INCREASE")
    assert positive.ok is True, positive.error
    assert positive.payload["consequences_applied"] == 1

    relationship = world_engine.get_relationship(
        instance.id,
        holder=SubjectRef(type=SubjectType.NPC, id=str(caretaker)),
        subject=SubjectRef(type=SubjectType.NPC, id=str(scout)),
        kind=RelationshipKind.TRUST,
    )
    # NEUTRAL → WARY → NEUTRAL: обе стороны сдвинули состояние одинаковым путём.
    assert relationship is not None and relationship.level is TrustLevel.NEUTRAL
    assert len(events_of_type(world_engine, instance, EventType.RELATIONSHIP_CHANGED)) == 2


# --- 12. идемпотентность ---------------------------------------------------


def test_duplicate_consequence_created_event_is_rejected(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    schedule(
        world_engine,
        instance,
        cause_event_ids=(last_event(world_engine, instance).id,),
        payload=informational_payload(caretaker),
    )
    event = events_of_type(world_engine, instance, EventType.CONSEQUENCE_CREATED)[0]
    assert event.payload["effect_payload"] == informational_payload(caretaker)
    events_before = len(world_engine.get_events(instance.id))

    with uow_factory() as uow:
        with pytest.raises(DomainError) as exc_info:
            uow.events.append(event)
        assert exc_info.value.code is ErrorCode.ALREADY_PROCESSED
        uow.rollback()

    assert len(world_engine.get_events(instance.id)) == events_before


def test_applied_consequence_is_not_applied_twice(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    result = schedule(
        world_engine,
        instance,
        cause_event_ids=(last_event(world_engine, instance).id,),
        payload=informational_payload(caretaker),
    )
    consequence_id = ConsequenceId(result.payload["consequence_id"])
    events_before = len(world_engine.get_events(instance.id))

    outcome = world_engine.pump_consequences(instance.id)

    assert outcome.applied == ()
    assert world_engine.get_consequence(instance.id, consequence_id).status is (
        ConsequenceStatus.APPLIED
    )
    assert len(world_engine.get_events(instance.id)) == events_before
    assert len(list(world_engine.get_npc_knowledge(instance.id, caretaker))) == 1


def test_effect_without_change_closes_consequence_without_event(
    world_engine: WorldEngine,
) -> None:
    """NPC уже знает: закрытие no-op последствия всё равно записывается."""
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    cause = last_event(world_engine, instance).id
    schedule(world_engine, instance, cause_event_ids=(cause,), payload=informational_payload(caretaker))
    events_before = len(world_engine.get_events(instance.id))

    second = schedule(
        world_engine, instance, cause_event_ids=(cause,), payload=informational_payload(caretaker)
    )

    assert second.ok is True
    assert second.payload["consequences_applied"] == 1
    new_events = world_engine.get_events(instance.id)[events_before:]
    assert [event.type for event in new_events] == [
        EventType.CONSEQUENCE_CREATED,
        EventType.CONSEQUENCE_APPLIED,
    ]
    consequence = world_engine.get_consequence(
        instance.id, ConsequenceId(second.payload["consequence_id"])
    )
    assert consequence.applied_event_id == new_events[-1].id
    assert len(events_of_type(world_engine, instance, EventType.NPC_LEARNED)) == 1


# --- 14. причина обязательна ------------------------------------------------


def test_consequence_with_unknown_cause_is_rejected(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    events_before = len(world_engine.get_events(instance.id))

    result = schedule(
        world_engine,
        instance,
        cause_event_ids=(EventId("ev_unknown"),),
        payload=informational_payload(caretaker),
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_FOUND
    assert world_engine.list_consequences(instance.id) == []
    assert len(world_engine.get_events(instance.id)) == events_before


def test_consequence_without_any_cause_is_rejected(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")

    result = schedule(world_engine, instance, cause_event_ids=(), payload=informational_payload(caretaker))

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ACTION


def test_cause_from_another_instance_is_rejected(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    caretaker = npc_id_by_key(world_engine, world_one, "caretaker")
    foreign_event = last_event(world_engine, world_two).id

    result = schedule(
        world_engine,
        world_one,
        cause_event_ids=(foreign_event,),
        payload=informational_payload(caretaker),
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_FOUND
    assert world_engine.list_consequences(world_one.id) == []
    assert world_engine.list_consequences(world_two.id) == []


# --- M1: лимит каскада ------------------------------------------------------


def test_cascade_limit_stops_without_rollback(tmp_path: Path) -> None:
    content_root = write_world_content(tmp_path, rule_count=20)
    world_engine, db_engine = make_engine(tmp_path, content_root)
    try:
        instance = make_world(world_engine)
        character = make_character(world_engine, instance)

        result = world_engine.inspect_information(
            instance.id, character_id=character, target_key="radio"
        )

        assert result.ok is True, result.error
        assert result.payload["cascade_limit_reached"] is True
        assert result.payload["consequences_applied"] == 16
        assert len(result.event_ids) >= 17  # action event and the applied consequences
        consequences = world_engine.list_consequences(instance.id)
        applied = [item for item in consequences if item.status is ConsequenceStatus.APPLIED]
        pending = [item for item in consequences if item.status is ConsequenceStatus.PENDING]
        assert len(applied) == 16  # MAX_CASCADE_STEPS
        assert len(pending) == 4   # M1: остановились, ничего не откатили
        assert world_engine.get_consequence(instance.id, applied[0].id).applied_event_id is not None
    finally:
        db_engine.dispose()


# --- M2: FAILED не блокирует каскад ----------------------------------------


def test_failed_consequence_does_not_block_cascade(tmp_path: Path) -> None:
    content_root = write_world_content(tmp_path, rule_count=2, include_bad_rule=True)
    world_engine, db_engine = make_engine(tmp_path, content_root)
    try:
        instance = make_world(world_engine)
        character = make_character(world_engine, instance)

        result = world_engine.inspect_information(
            instance.id, character_id=character, target_key="radio"
        )

        assert result.ok is True, result.error
        assert result.payload["consequences_failed"] == 1
        assert result.payload["consequences_applied"] == 2
        statuses = {item.status for item in world_engine.list_consequences(instance.id)}
        assert statuses == {ConsequenceStatus.FAILED, ConsequenceStatus.APPLIED}
        failed_event = events_of_type(world_engine, instance, EventType.CONSEQUENCE_FAILED)
        assert len(failed_event) == 1
        assert failed_event[0].payload["effect"] == ConsequenceEffect.PHYSICAL_RELOCATE.value
    finally:
        db_engine.dispose()


# --- правила из контента ----------------------------------------------------


def test_shipped_content_has_no_rules() -> None:
    """Правила не шипаются: иначе старые сценарии увидели бы новые события."""
    assert load_content_catalog("content").rules == {}


def test_rule_creates_consequence_from_event(tmp_path: Path) -> None:
    content_root = write_world_content(tmp_path, rule_count=1, trigger={"kind": "AFTER_TICKS", "delay_ticks": 2})
    world_engine, db_engine = make_engine(tmp_path, content_root)
    try:
        instance = make_world(world_engine)
        character = make_character(world_engine, instance)

        result = world_engine.inspect_information(
            instance.id, character_id=character, target_key="radio"
        )

        assert result.ok is True, result.error
        consequences = world_engine.list_consequences(instance.id)
        assert len(consequences) == 1
        consequence = consequences[0]
        assert consequence.rule_key == "rule_00"
        assert consequence.status is ConsequenceStatus.PENDING
        assert consequence.causes[0].origin is CauseOrigin.ACTOR

        # Повторный прогон насоса не создаёт дубль (идемпотентность материала).
        world_engine.pump_consequences(instance.id)
        assert len(world_engine.list_consequences(instance.id)) == 1

        due_tick = consequence.due_tick
        while world_engine.get_instance(instance.id).state.world_tick < due_tick:
            world_engine.advance_tick(instance.id)
        assert world_engine.get_consequence(instance.id, consequence.id).status is (
            ConsequenceStatus.APPLIED
        )
        keeper = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == "keeper")
        assert len(list(world_engine.get_npc_knowledge(instance.id, keeper.id))) == 1
    finally:
        db_engine.dispose()


def test_rule_with_missing_instance_subject_is_reported(tmp_path: Path) -> None:
    """Дрейф контента: правило ссылается на NPC, которого нет в этом мире."""
    content_root = write_world_content(tmp_path, rule_count=0)
    world_engine, db_engine = make_engine(tmp_path, content_root)
    try:
        instance = make_world(world_engine)
        character = make_character(world_engine, instance)

        drifted_root = write_world_content(
            tmp_path / "drifted", rule_count=0, extra_rule_npc_key="ghost"
        )
        drifted_engine = WorldEngine(
            uow_factory=lambda: SqlAlchemyUnitOfWork(create_session_factory(db_engine)),
            catalog=load_content_catalog(drifted_root),
        )
        result = drifted_engine.inspect_information(
            instance.id, character_id=character, target_key="radio"
        )

        assert result.ok is True, result.error
        assert result.payload["consequence_rules_failed"] == ("drifted_rule",)
        assert world_engine.list_consequences(instance.id) == []
    finally:
        db_engine.dispose()


# --- контент для тестов -----------------------------------------------------


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_world_content(
    root: Path,
    *,
    rule_count: int = 0,
    trigger: dict[str, Any] | None = None,
    include_bad_rule: bool = False,
    extra_rule_npc_key: str | None = None,
) -> Path:
    """Минимальный мир для проверки последствий + правила контента."""
    _write_json(
        root / "manifest.json",
        {"version": "v1", "start_location": "base"},
    )
    _write_json(
        root / "locations" / "base.json",
        {
            "key": "base",
            "name": "База",
            "type": "BASE",
            "description": "Начало.",
            "connections": ["forest"],
        },
    )
    _write_json(
        root / "locations" / "forest.json",
        {
            "key": "forest",
            "name": "Лес",
            "type": "WILD",
            "description": "Лес.",
            "connections": ["base"],
        },
    )
    # Руины ни с чем не соединены: сюда нельзя переместить NPC — эффект провалится.
    _write_json(
        root / "locations" / "ruins.json",
        {
            "key": "ruins",
            "name": "Руины",
            "type": "RUINS",
            "description": "Руины.",
            "connections": [],
        },
    )
    _write_json(
        root / "information" / "radio.json",
        {
            "key": "radio",
            "location_key": "base",
            "type": "DEVICE",
            "source": "PHYSICAL_OBJECT",
            "authenticity": "AUTHENTIC",
            "access": "OPEN",
            "content": "Корпус вскрыт.",
            "truth": "Корпус вскрыт намеренно.",
        },
    )
    _write_json(
        root / "npcs" / "keeper.json",
        {
            "key": "keeper",
            "name": "Смотритель",
            "description": "Описание.",
            "initial_location": "base",
            "goals": ["KEEP_BASE"],
        },
    )
    _write_json(
        root / "npcs" / "scout.json",
        {
            "key": "scout",
            "name": "Разведчик",
            "description": "Описание.",
            "initial_location": "forest",
            "goals": ["SCOUT"],
        },
    )
    if extra_rule_npc_key is not None:
        _write_json(
            root / "npcs" / "ghost.json",
            {
                "key": "ghost",
                "name": "Призрак",
                "description": "Описание.",
                "initial_location": "forest",
                "goals": ["HAUNT"],
            },
        )
        _write_json(
            root / "consequences" / "drifted_rule.json",
            {
                "key": "drifted_rule",
                "on_event_type": "INFORMATION_DISCOVERED",
                "when_payload": {"information_key": "radio"},
                "type": "INFORMATIONAL",
                "scale": "LOCAL",
                "visibility": "HIDDEN",
                "trigger": {"kind": "IMMEDIATE"},
                "effect": {
                    "kind": "INFORMATIONAL_LEARN",
                    "npc_key": extra_rule_npc_key,
                    "information_key": "radio",
                },
            },
        )

    rule_trigger = trigger or {"kind": "IMMEDIATE"}
    for index in range(rule_count):
        _write_json(
            root / "consequences" / f"rule_{index:02d}.json",
            {
                "key": f"rule_{index:02d}",
                "on_event_type": "INFORMATION_DISCOVERED",
                "when_payload": {"information_key": "radio"},
                "type": "INFORMATIONAL",
                "scale": "LOCAL",
                "visibility": "HIDDEN",
                "trigger": rule_trigger,
                "effect": {
                    "kind": "INFORMATIONAL_LEARN",
                    "npc_key": "keeper",
                    "information_key": "radio",
                },
            },
        )
    if include_bad_rule:
        _write_json(
            root / "consequences" / "bad_rule.json",
            {
                "key": "bad_rule",
                "on_event_type": "INFORMATION_DISCOVERED",
                "when_payload": {"information_key": "radio"},
                "type": "PHYSICAL",
                "scale": "LOCAL",
                "visibility": "VISIBLE",
                "trigger": {"kind": "IMMEDIATE"},
                "effect": {
                    "kind": "PHYSICAL_RELOCATE",
                    "npc_key": "keeper",
                    "to_location_key": "ruins",
                },
            },
        )
    return root


def make_engine(tmp_path: Path, content_root: Path):  # noqa: ANN201
    from world_error.infrastructure.db.engine import create_db_engine, create_session_factory
    from world_error.infrastructure.db.tables import metadata

    db_engine = create_db_engine(f"sqlite+pysqlite:///{(tmp_path / 'consequences.db').as_posix()}")
    metadata.create_all(db_engine)
    session_factory = create_session_factory(db_engine)
    world_engine = WorldEngine(
        uow_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
        catalog=load_content_catalog(content_root),
    )
    return world_engine, db_engine
