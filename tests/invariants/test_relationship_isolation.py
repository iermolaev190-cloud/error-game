"""Инварианты: отношения не пересекают INSTANCE и не раскрываются игроку.

M3: ни проекция локации, ни show-* не должны содержать ни одного признака
отношений — ни вида, ни ступени, ни идентификатора записи.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Callable

from world_error.application.queries.location_view import (
    CharacterPresence,
    LocationView,
    NpcPresence,
)
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import (
    RelationshipDirection,
    RelationshipKind,
    SubjectRef,
    TrustLevel,
)
from world_error.domain.relationships.rules import SignificantAction
from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

BASE = LocationKey("base")
FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")

RELATIONSHIP_TOKENS = (
    "TRUST",
    "SUSPICION",
    "HOSTILE",
    "WARY",
    "NEUTRAL",
    "FRIENDLY",
    "DEVOTED",
    "NONE",
    "LOW",
    "MEDIUM",
    "HIGH",
    "RELATIONSHIP_CHANGED",
)


def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def npc_by_key(world_engine: WorldEngine, instance: WorldInstance, key: str) -> SubjectRef:
    npc = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == key)
    return SubjectRef(type=SubjectType.NPC, id=str(npc.id))


def make_character(
    world_engine: WorldEngine, instance: WorldInstance, player_id: str = "player-a"
) -> SubjectRef:
    result = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert result.ok is True, result.error
    return SubjectRef(type=SubjectType.CHARACTER, id=result.payload["character_id"])


def assert_no_relationship_tokens(rendered: str) -> None:
    pattern = r"\b(" + "|".join(re.escape(token) for token in RELATIONSHIP_TOKENS) + r")\b"
    leaked = sorted(set(re.findall(pattern, rendered)))
    assert not leaked, f"утечка отношений: {leaked}\n{rendered}"
    assert "rel_" not in rendered, f"утечка id отношения:\n{rendered}"


def test_relationships_do_not_leak_between_instances(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    npc_one = npc_by_key(world_engine, world_one, "mechanic")
    npc_two = npc_by_key(world_engine, world_two, "mechanic")
    character_one = make_character(world_engine, world_one)
    character_two = make_character(world_engine, world_two, "player-b")

    assert world_engine.change_relationship(
        world_one.id,
        holder=npc_one,
        subject=character_one,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    ).ok is True

    # Второй мир ничего об этом не знает.
    assert (
        world_engine.get_relationship(
            world_two.id, holder=npc_two, subject=character_two, kind=RelationshipKind.TRUST
        )
        is None
    )
    assert world_engine.list_relationships_of(world_two.id, npc_two) == []
    assert world_engine.list_relationships_about(world_two.id, character_two) == []
    assert [event.type for event in world_engine.get_events(world_two.id)] == [
        EventType.WORLD_INSTANCE_CREATED,
        EventType.CHARACTER_CREATED,
    ]


def test_asymmetric_rows_persist_and_stay_independent(
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
    assert world_engine.change_relationship(
        instance.id,
        holder=character,
        subject=npc,
        kind=RelationshipKind.SUSPICION,
        direction=RelationshipDirection.INCREASE,
    ).ok is True

    with uow_factory() as uow:
        forward = uow.relationships.find(instance.id, npc, character, RelationshipKind.TRUST)
        backward = uow.relationships.find(instance.id, character, npc, RelationshipKind.TRUST)
        reverse_suspicion = uow.relationships.find(
            instance.id, character, npc, RelationshipKind.SUSPICION
        )

    assert forward is not None and forward.level is TrustLevel.FRIENDLY
    assert backward is None
    assert reverse_suspicion is not None
    assert len(list(world_engine.list_relationships_of(instance.id, npc))) == 1
    assert len(list(world_engine.list_relationships_of(instance.id, character))) == 1


def test_location_view_has_no_relationship_fields() -> None:
    """M3: отношения не могут попасть в проекцию структурно."""
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


def test_location_view_does_not_reveal_relationships(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "caretaker")
    character = make_character(world_engine, instance)

    assert world_engine.apply_significant_action(
        instance.id, actor=character, holder=npc, action=SignificantAction.BETRAYED
    ).ok is True

    view = world_engine.view_location(
        instance.id, observer_id=CharacterId(character.id), location_key=BASE
    )

    assert_no_relationship_tokens(repr(view))
    # NPC всё ещё виден как публичный факт локации.
    assert [presence.name for presence in view.npcs] == ["Смотритель"]


def test_relationship_changes_do_not_leak_into_public_facts(
    world_engine: WorldEngine,
) -> None:
    """Публичные факты одинаковы до и после изменения отношения."""
    instance = make_world(world_engine)
    character = make_character(world_engine, instance)
    before = world_engine.view_location(
        instance.id, observer_id=CharacterId(character.id), location_key=BASE
    )

    npc = npc_by_key(world_engine, instance, "caretaker")
    assert world_engine.change_relationship(
        instance.id,
        holder=npc,
        subject=character,
        kind=RelationshipKind.SUSPICION,
        direction=RelationshipDirection.INCREASE,
    ).ok is True

    after = world_engine.view_location(
        instance.id, observer_id=CharacterId(character.id), location_key=BASE
    )
    assert before.npcs == after.npcs
    assert before.characters == after.characters
    assert before.discovery_state == after.discovery_state
    assert_no_relationship_tokens(repr(after))


def test_relationship_change_does_not_touch_world_visibility(
    world_engine: WorldEngine,
) -> None:
    """Изменение отношения не «обнаруживает» локации и не трогает информацию."""
    instance = make_world(world_engine)
    npc = npc_by_key(world_engine, instance, "mechanic")
    character = make_character(world_engine, instance)
    information_before = world_engine.get_information(instance.id, "damaged_radio")
    locations_before = {
        item.key: item.discovery_state for item in world_engine.get_locations(instance.id)
    }

    assert world_engine.change_relationship(
        instance.id,
        holder=npc,
        subject=character,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.DECREASE,
    ).ok is True

    information_after = world_engine.get_information(instance.id, "damaged_radio")
    assert information_after.discovery_state is information_before.discovery_state
    assert information_after.discovered_by == information_before.discovered_by
    locations_after = {
        item.key: item.discovery_state for item in world_engine.get_locations(instance.id)
    }
    assert locations_after == locations_before
    assert FOREST in locations_after and OLD_STATION in locations_after
