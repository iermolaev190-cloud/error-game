"""Death invariants: event cause, no inherited state, retained history, isolation."""

from __future__ import annotations

import dataclasses

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import CharacterActivity, CharacterLifecycle
from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import (
    RelationshipDirection,
    RelationshipKind,
    SubjectRef,
)
from world_error.domain.shared.kernel import CharacterId, ErrorCode, EventId, LocationKey
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.tables import characters


def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def make_character(world_engine: WorldEngine, instance: WorldInstance, player_id: str) -> CharacterId:
    created = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert created.ok is True, created.error
    return CharacterId(created.payload["character_id"])


def test_death_without_cause_is_rejected(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    character_id = make_character(world_engine, instance, "player-a")
    stable_death_event_id = EventId("ev_death_retry")

    missing = world_engine.kill_character(
        instance.id,
        character_id,
        cause_event_id=EventId(""),
        death_event_id=stable_death_event_id,
    )
    assert missing.ok is False
    assert missing.error is not None and missing.error.code is ErrorCode.INVALID_ACTION
    assert world_engine.get_character(instance.id, character_id).lifecycle is CharacterLifecycle.ALIVE


def test_death_event_is_idempotent(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    character_id = make_character(world_engine, instance, "player-a")
    cause_event_id = world_engine.get_events(instance.id)[-1].id
    stable_death_event_id = EventId("ev_death_retry")

    died = world_engine.kill_character(
        instance.id,
        character_id,
        cause_event_id=cause_event_id,
        death_event_id=stable_death_event_id,
    )
    assert died.ok is True, died.error
    dead = world_engine.get_character(instance.id, character_id)
    assert dead.lifecycle is CharacterLifecycle.DEAD
    assert dead.death_event_id == stable_death_event_id
    assert dead.death_cause_event_id == cause_event_id
    assert world_engine.get_events(instance.id)[-1].type is EventType.DEATH_EVENT

    retried = world_engine.kill_character(
        instance.id,
        character_id,
        cause_event_id=cause_event_id,
        death_event_id=stable_death_event_id,
    )
    assert retried.ok is False
    assert retried.error is not None and retried.error.code is ErrorCode.ALREADY_PROCESSED
    assert world_engine.get_character(instance.id, character_id).lifecycle is CharacterLifecycle.DEAD
    assert len([event for event in world_engine.get_events(instance.id) if event.id == stable_death_event_id]) == 1


def test_dead_character_cannot_move_inspect_share_or_change_relationship(
    world_engine: WorldEngine,
) -> None:
    instance = make_world(world_engine)
    dead_id = make_character(world_engine, instance, "player-a")
    living_id = make_character(world_engine, instance, "player-b")
    cause_event_id = world_engine.get_events(instance.id)[-1].id
    died = world_engine.die_character(instance.id, dead_id, cause_event_id=cause_event_id)
    assert died.ok is True, died.error

    move = world_engine.move_character(
        instance.id, character_id=dead_id, to_location_key=LocationKey("forest")
    )
    inspect_result = world_engine.inspect_information(
        instance.id, character_id=dead_id, target_key="damaged_radio"
    )
    share = world_engine.share_knowledge(
        instance.id,
        sharer_id=dead_id,
        receiver_id=living_id,
        information_key="damaged_radio",
    )
    npc = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == "mechanic")
    relation_as_holder = world_engine.change_relationship(
        instance.id,
        holder=SubjectRef(type=SubjectType.CHARACTER, id=str(dead_id)),
        subject=SubjectRef(type=SubjectType.NPC, id=str(npc.id)),
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    )
    relation_as_target = world_engine.change_relationship(
        instance.id,
        holder=SubjectRef(type=SubjectType.NPC, id=str(npc.id)),
        subject=SubjectRef(type=SubjectType.CHARACTER, id=str(dead_id)),
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    )

    for result in (move, inspect_result, share, relation_as_holder, relation_as_target):
        assert result.ok is False
        assert result.error is not None and result.error.code is ErrorCode.NOT_ALLOWED


def test_new_character_does_not_inherit_knowledge(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    old_id = make_character(world_engine, instance, "player-a")
    for location in ("forest", "old_station"):
        moved = world_engine.move_character(
            instance.id, character_id=old_id, to_location_key=LocationKey(location)
        )
        assert moved.ok is True, moved.error
    learned = world_engine.inspect_information(
        instance.id, character_id=old_id, target_key="damaged_radio"
    )
    assert learned.ok is True, learned.error
    npc = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == "caretaker")
    relation = world_engine.change_relationship(
        instance.id,
        holder=SubjectRef(type=SubjectType.CHARACTER, id=str(old_id)),
        subject=SubjectRef(type=SubjectType.NPC, id=str(npc.id)),
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    )
    assert relation.ok is True, relation.error
    cause_event_id = world_engine.get_events(instance.id)[-1].id
    death = world_engine.kill_character(instance.id, old_id, cause_event_id=cause_event_id)
    assert death.ok is True, death.error

    new_id = world_engine.spawn_new_character(instance.id, player_id="player-a", name="New")
    assert new_id.ok is True, new_id.error
    new_character_id = CharacterId(new_id.payload["character_id"])
    assert list(world_engine.get_knowledge(instance.id, new_character_id)) == []
    assert world_engine.get_relationship(
        instance.id,
        holder=SubjectRef(type=SubjectType.CHARACTER, id=str(new_character_id)),
        subject=SubjectRef(type=SubjectType.NPC, id=str(npc.id)),
        kind=RelationshipKind.TRUST,
    ) is None
    assert world_engine.get_relationship(
        instance.id,
        holder=SubjectRef(type=SubjectType.CHARACTER, id=str(old_id)),
        subject=SubjectRef(type=SubjectType.NPC, id=str(npc.id)),
        kind=RelationshipKind.TRUST,
    ) is not None

    assert "predecessor_id" not in {field.name for field in dataclasses.fields(world_engine.get_character(instance.id, new_character_id))}
    assert "inventory" not in characters.c
    assert "knowledge" not in characters.c


def test_npc_knowledge_of_old_character_context_survives_death(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    old_id = make_character(world_engine, instance, "player-a")
    npc = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == "mechanic")
    learned = world_engine.npc_observe_information(
        instance.id, npc_id=npc.id, information_key="damaged_radio"
    )
    assert learned.ok is True, learned.error
    npc_knowledge_before = list(world_engine.get_npc_knowledge(instance.id, npc.id))
    for location in ("forest", "old_station"):
        moved = world_engine.move_character(
            instance.id, character_id=old_id, to_location_key=LocationKey(location)
        )
        assert moved.ok is True, moved.error
    player_knowledge = world_engine.inspect_information(
        instance.id, character_id=old_id, target_key="damaged_radio"
    )
    assert player_knowledge.ok is True, player_knowledge.error

    cause_event_id = world_engine.get_events(instance.id)[-1].id
    death = world_engine.kill_character(instance.id, old_id, cause_event_id=cause_event_id)
    assert death.ok is True, death.error

    assert world_engine.get_npc_knowledge(instance.id, npc.id) == npc_knowledge_before
    assert len(world_engine.get_knowledge(instance.id, old_id)) == 1


def test_inactive_character_stays_alive_after_one_hundred_ticks(
    world_engine: WorldEngine, uow_factory
) -> None:  # noqa: ANN001
    instance = make_world(world_engine)
    character_id = make_character(world_engine, instance, "inactive-player")
    with uow_factory() as uow:
        character = uow.characters.get(instance.id, character_id)
        character.activity = CharacterActivity.INACTIVE
        uow.characters.save(character)
        uow.commit()

    for index in range(100):
        world_engine.advance_tick(instance.id, cause=f"inactive-{index}")

    character = world_engine.get_character(instance.id, character_id)
    assert character.activity is CharacterActivity.INACTIVE
    assert character.lifecycle is CharacterLifecycle.ALIVE


def test_death_and_action_cost_are_isolated_between_instances(world_engine: WorldEngine) -> None:
    world_a = make_world(world_engine, -1001)
    world_b = make_world(world_engine, -1002)
    character_a = make_character(world_engine, world_a, "player-a")
    cost_character_a = make_character(world_engine, world_a, "player-cost")
    character_b = make_character(world_engine, world_b, "player-b")
    tick_b_before = world_engine.get_instance(world_b.id).state.world_tick
    cause_event_id = world_engine.get_events(world_a.id)[-1].id

    death = world_engine.kill_character(world_a.id, character_a, cause_event_id=cause_event_id)
    assert death.ok is True, death.error
    moved = world_engine.move_character(
        world_a.id,
        character_id=cost_character_a,
        to_location_key=LocationKey("forest"),
        cost_ticks=3,
    )
    assert moved.ok is True, moved.error
    assert world_engine.get_character(world_b.id, character_b).lifecycle is CharacterLifecycle.ALIVE
    assert world_engine.get_instance(world_b.id).state.world_tick == tick_b_before
    assert world_engine.get_character(world_a.id, character_a).lifecycle is CharacterLifecycle.DEAD
