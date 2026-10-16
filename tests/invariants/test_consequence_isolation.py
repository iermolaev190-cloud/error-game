"""Инварианты: последствия не раскрываются игроку и не пересекают INSTANCE.

7/8: игрок видит изменившийся мир, но не видит ни последствия, ни его причины.
11: последствия одного INSTANCE не видны в другом.
M4: пути «последствие → знание игрока» не существует.
M9: payload переживает round-trip через JSON-колонку один в один.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Callable

import pytest

from world_error.application.queries.location_view import CharacterPresence, LocationView, NpcPresence
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.consequences.consequence import ConsequenceTrigger
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceStatus,
    ConsequenceType,
    ConsequenceVisibility,
)
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import RelationshipKind, SubjectRef, TrustLevel
from world_error.domain.shared.kernel import CharacterId, ConsequenceId, LocationKey
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

BASE = LocationKey("base")
INFO_KEY = "damaged_radio"

CONSEQUENCE_TOKENS = (
    "CONSEQUENCE",
    "consequence",
    "INFORMATIONAL",
    "RELATIONAL",
    "PHYSICAL",
    "IMMEDIATE",
    "AFTER_TICKS",
    "ON_EVENT_TYPE",
    "PERSONAL",
    "LOCAL",
    "REGIONAL",
    "GLOBAL",
    "VISIBLE",
    "PARTIALLY_VISIBLE",
    "HIDDEN",
    "INDIRECT",
    "UNKNOWN",
    "INFORMATIONAL_LEARN",
    "RELATIONAL_SHIFT",
    "PHYSICAL_STATUS_CHANGE",
    "PHYSICAL_RELOCATE",
)


def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def npc_by_key(world_engine: WorldEngine, instance: WorldInstance, key: str) -> SubjectRef:
    npc = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == key)
    return SubjectRef(type=SubjectType.NPC, id=str(npc.id))


def npc_id_by_key(world_engine: WorldEngine, instance: WorldInstance, key: str):
    return next(npc.id for npc in world_engine.get_npcs(instance.id) if npc.key == key)


def make_character(
    world_engine: WorldEngine, instance: WorldInstance, player_id: str = "player-a"
) -> CharacterId:
    result = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert result.ok is True, result.error
    return CharacterId(result.payload["character_id"])


def last_event_id(world_engine: WorldEngine, instance: WorldInstance):
    return world_engine.get_events(instance.id)[-1].id


def schedule_learn(
    world_engine: WorldEngine,
    instance: WorldInstance,
    *,
    npc_id,
    payload_extra: dict | None = None,
    visibility: ConsequenceVisibility = ConsequenceVisibility.HIDDEN,
    scale: ConsequenceScale = ConsequenceScale.LOCAL,
):
    payload = {"npc_id": str(npc_id), "information_key": INFO_KEY}
    payload.update(payload_extra or {})
    return world_engine.schedule_consequence(
        instance.id,
        cause_event_ids=(last_event_id(world_engine, instance),),
        type=ConsequenceType.INFORMATIONAL,
        scale=scale,
        visibility=visibility,
        trigger=ConsequenceTrigger.immediate(),
        effect=ConsequenceEffect.INFORMATIONAL_LEARN,
        payload=payload,
    )


def assert_no_consequence_tokens(rendered: str) -> None:
    pattern = r"\b(" + "|".join(re.escape(token) for token in CONSEQUENCE_TOKENS) + r")\b"
    leaked = sorted(set(re.findall(pattern, rendered)))
    assert not leaked, f"утечка последствий: {leaked}\n{rendered}"
    assert "csq_" not in rendered, f"утечка id последствия:\n{rendered}"


def test_consequence_never_writes_player_knowledge(world_engine: WorldEngine) -> None:
    """M4: последствие пишет знание NPC, а знание персонажа не трогает вообще."""
    instance = make_world(world_engine)
    character = make_character(world_engine, instance)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")

    result = schedule_learn(world_engine, instance, npc_id=caretaker)

    assert result.ok is True, result.error
    assert len(list(world_engine.get_npc_knowledge(instance.id, caretaker))) == 1
    assert list(world_engine.get_knowledge(instance.id, character)) == []


def test_player_does_not_see_cause_of_visible_world_change(world_engine: WorldEngine) -> None:
    """§28: последствие заметно как изменение мира, но причина — нет."""
    instance = make_world(world_engine)
    character = make_character(world_engine, instance)
    caretaker = npc_by_key(world_engine, instance, "caretaker")
    scout = npc_by_key(world_engine, instance, "scout")

    view_before = world_engine.view_location(
        instance.id, observer_id=character, location_key=BASE
    )
    result = world_engine.schedule_consequence(
        instance.id,
        cause_event_ids=(last_event_id(world_engine, instance),),
        type=ConsequenceType.RELATIONAL,
        scale=ConsequenceScale.PERSONAL,
        visibility=ConsequenceVisibility.HIDDEN,
        trigger=ConsequenceTrigger.immediate(),
        effect=ConsequenceEffect.RELATIONAL_SHIFT,
        payload={
            "holder_type": "NPC",
            "holder_id": caretaker.id,
            "subject_type": "NPC",
            "subject_id": scout.id,
            "kind": "TRUST",
            "direction": "DECREASE",
        },
    )
    assert result.ok is True, result.error
    assert result.payload["consequences_applied"] == 1

    # Мир изменился: отношение NPC → NPC стало хуже.
    relationship = world_engine.get_relationship(
        instance.id, holder=caretaker, subject=scout, kind=RelationshipKind.TRUST
    )
    assert relationship is not None and relationship.level is TrustLevel.WARY

    # Публичная проекция не изменилась и не содержит признаков последствий.
    view_after = world_engine.view_location(instance.id, observer_id=character, location_key=BASE)
    assert view_after.npcs == view_before.npcs
    assert view_after.characters == view_before.characters
    assert view_after.discovery_state == view_before.discovery_state
    assert_no_consequence_tokens(repr(view_after))
    assert list(world_engine.get_knowledge(instance.id, character)) == []


def test_public_projection_has_no_consequence_fields(world_engine: WorldEngine) -> None:
    assert {field.name for field in dataclasses.fields(LocationView)} == {
        "world_instance_id",
        "location_key",
        "name",
        "type",
        "description",
        "discovery_state",
        "characters",
        "npcs",
        "items",
        "connections",
    }
    assert {field.name for field in dataclasses.fields(CharacterPresence)} == {
        "character_id",
        "name",
        "activity",
    }
    assert {field.name for field in dataclasses.fields(NpcPresence)} == {
        "npc_id",
        "name",
        "status",
    }


@pytest.mark.parametrize(
    "visibility",
    [ConsequenceVisibility.VISIBLE, ConsequenceVisibility.HIDDEN, ConsequenceVisibility.UNKNOWN],
)
def test_any_visibility_stays_invisible_to_player(
    world_engine: WorldEngine, visibility: ConsequenceVisibility
) -> None:
    instance = make_world(world_engine)
    character = make_character(world_engine, instance)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")

    result = schedule_learn(world_engine, instance, npc_id=caretaker, visibility=visibility)

    assert result.ok is True
    view = world_engine.view_location(instance.id, observer_id=character, location_key=BASE)
    assert_no_consequence_tokens(repr(view))
    assert list(world_engine.get_knowledge(instance.id, character)) == []


def test_consequences_do_not_cross_instances(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    caretaker_one = npc_id_by_key(world_engine, world_one, "caretaker")
    caretaker_two = npc_id_by_key(world_engine, world_two, "caretaker")

    result = schedule_learn(world_engine, world_one, npc_id=caretaker_one)
    assert result.ok is True

    assert world_engine.list_consequences(world_two.id) == []
    assert list(world_engine.get_npc_knowledge(world_two.id, caretaker_two)) == []
    assert [event.type.value for event in world_engine.get_events(world_two.id)] == [
        "WORLD_INSTANCE_CREATED"
    ]


def test_consequence_payload_round_trips_through_json(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    """M9: payload переживает сериализацию один в один, включая кавычки и переводы строк."""
    instance = make_world(world_engine)
    caretaker = npc_id_by_key(world_engine, instance, "caretaker")
    extra = {
        "claim": 'Корпус вскрыт «изнутри».\nВторая строка.',
        "claim_type": "RUMOR",
        "confidence": "UNCERTAIN",
    }
    result = schedule_learn(world_engine, instance, npc_id=caretaker, payload_extra=extra)
    assert result.ok is True, result.error
    consequence_id = ConsequenceId(result.payload["consequence_id"])

    expected = {"npc_id": str(caretaker), "information_key": INFO_KEY, **extra}
    first = world_engine.get_consequence(instance.id, consequence_id)
    assert dict(first.payload) == expected

    # Новая сессия и новый объект: читаем то же самое.
    with uow_factory() as uow:
        again = uow.consequences.get(instance.id, consequence_id)
    assert dict(again.payload) == expected
    assert again.status is ConsequenceStatus.APPLIED

    knowledge = list(world_engine.get_npc_knowledge(instance.id, caretaker))[0]
    assert knowledge.claim == extra["claim"]
