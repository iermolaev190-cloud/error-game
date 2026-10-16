"""Legacy documents are discovered in-world and remain instance-scoped."""

from __future__ import annotations

import dataclasses

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import CharacterLifecycle
from world_error.domain.shared.kernel import CharacterId, ErrorCode, LegacyDocumentId
from world_error.domain.world.instance import WorldInstance


def make_world(world_engine: WorldEngine, chat_id: int) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def make_character(world_engine: WorldEngine, instance: WorldInstance, player_id: str) -> CharacterId:
    result = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert result.ok is True, result.error
    return CharacterId(result.payload["character_id"])


def test_new_character_finds_legacy_document_through_world_not_account_link(
    world_engine: WorldEngine,
) -> None:
    instance = make_world(world_engine, -1001)
    old_id = make_character(world_engine, instance, "same-player")
    cause_event_id = world_engine.get_events(instance.id)[-1].id
    death = world_engine.kill_character(instance.id, old_id, cause_event_id=cause_event_id)
    assert death.ok is True, death.error
    left = world_engine.leave_legacy_document(
        instance.id,
        character_id=old_id,
        document_key="last-note",
        content="Маршрут отмечен на обороте карты.",
    )
    assert left.ok is True, left.error
    document_id = LegacyDocumentId(left.payload["document_id"])

    spawned = world_engine.spawn_new_character(
        instance.id, player_id="same-player", name="Новый персонаж"
    )
    assert spawned.ok is True, spawned.error
    new_id = CharacterId(spawned.payload["character_id"])
    assert world_engine.get_character(instance.id, old_id).lifecycle is CharacterLifecycle.DEAD
    assert world_engine.get_character(instance.id, new_id).lifecycle is CharacterLifecycle.ALIVE

    found = world_engine.inspect_legacy_document(
        instance.id, character_id=new_id, document_id=document_id
    )

    assert found.ok is True, found.error
    assert found.payload["already_known"] is False
    assert found.payload["content"] == "Маршрут отмечен на обороте карты."
    event = world_engine.get_events(instance.id)[-1]
    assert event.target == str(document_id)
    assert event.payload["content"] == "Маршрут отмечен на обороте карты."
    assert "predecessor_id" not in {
        field.name for field in dataclasses.fields(world_engine.get_character(instance.id, new_id))
    }


def test_legacy_document_does_not_cross_instances(world_engine: WorldEngine) -> None:
    world_a = make_world(world_engine, -1001)
    world_b = make_world(world_engine, -1002)
    old_id = make_character(world_engine, world_a, "player-a")
    cause_event_id = world_engine.get_events(world_a.id)[-1].id
    death = world_engine.kill_character(world_a.id, old_id, cause_event_id=cause_event_id)
    assert death.ok is True, death.error
    left = world_engine.leave_legacy_document(
        world_a.id,
        character_id=old_id,
        document_key="world-a-note",
        content="Только в мире A.",
    )
    assert left.ok is True, left.error
    new_b = make_character(world_engine, world_b, "player-b")

    result = world_engine.inspect_legacy_document(
        world_b.id,
        character_id=new_b,
        document_id=LegacyDocumentId(left.payload["document_id"]),
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_FOUND
