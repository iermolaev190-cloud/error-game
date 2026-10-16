"""Integration: consequence cancellation and transformation are events."""

from __future__ import annotations

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.consequences.consequence import ConsequenceTrigger
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceStatus,
    ConsequenceType,
    ConsequenceVisibility,
)
from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import ConsequenceId, ErrorCode
from world_error.domain.world.instance import WorldInstance


def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def schedule_pending(world_engine: WorldEngine, instance: WorldInstance) -> ConsequenceId:
    cause = world_engine.get_events(instance.id)[-1].id
    result = world_engine.schedule_consequence(
        instance.id,
        cause_event_ids=(cause,),
        type=ConsequenceType.INFORMATIONAL,
        scale=ConsequenceScale.LOCAL,
        visibility=ConsequenceVisibility.HIDDEN,
        trigger=ConsequenceTrigger.after_ticks(100),
        effect=ConsequenceEffect.INFORMATIONAL_LEARN,
        payload={
            "npc_id": str(next(npc.id for npc in world_engine.get_npcs(instance.id) if npc.key == "caretaker")),
            "information_key": "damaged_radio",
        },
    )
    assert result.ok is True, result.error
    return ConsequenceId(result.payload["consequence_id"])


def test_cancel_consequence_creates_event(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    consequence_id = schedule_pending(world_engine, instance)
    event_count = len(world_engine.get_events(instance.id))

    cancelled = world_engine.cancel_consequence(instance.id, consequence_id)

    assert cancelled.ok is True, cancelled.error
    assert len(world_engine.get_events(instance.id)) == event_count + 1
    assert world_engine.get_events(instance.id)[-1].type is EventType.CONSEQUENCE_CANCELLED
    assert world_engine.get_consequence(instance.id, consequence_id).status is ConsequenceStatus.CANCELLED
    assert world_engine.pump_time(instance.id).consequences.applied == ()

    repeated = world_engine.cancel_consequence(instance.id, consequence_id)
    assert repeated.ok is True, repeated.error
    assert repeated.payload["already_cancelled"] is True
    assert len(world_engine.get_events(instance.id)) == event_count + 1


def test_transform_applied_consequence_is_rejected(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    cause = world_engine.get_events(instance.id)[-1].id
    applied = world_engine.schedule_consequence(
        instance.id,
        cause_event_ids=(cause,),
        type=ConsequenceType.INFORMATIONAL,
        scale=ConsequenceScale.LOCAL,
        visibility=ConsequenceVisibility.HIDDEN,
        trigger=ConsequenceTrigger.immediate(),
        effect=ConsequenceEffect.INFORMATIONAL_LEARN,
        payload={
            "npc_id": str(next(npc.id for npc in world_engine.get_npcs(instance.id) if npc.key == "caretaker")),
            "information_key": "damaged_radio",
        },
    )
    assert applied.ok is True, applied.error
    consequence_id = ConsequenceId(applied.payload["consequence_id"])
    replacement = {
        "type": ConsequenceType.INFORMATIONAL,
        "scale": ConsequenceScale.REGIONAL,
        "visibility": ConsequenceVisibility.HIDDEN,
        "trigger": ConsequenceTrigger.after_ticks(10),
        "effect": ConsequenceEffect.INFORMATIONAL_LEARN,
        "payload": dict(world_engine.get_consequence(instance.id, consequence_id).payload),
    }

    result = world_engine.transform_consequence(instance.id, consequence_id, **replacement)

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ACTION


def test_cancel_applied_consequence_is_rejected(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    cause = world_engine.get_events(instance.id)[-1].id
    applied = world_engine.schedule_consequence(
        instance.id,
        cause_event_ids=(cause,),
        type=ConsequenceType.INFORMATIONAL,
        scale=ConsequenceScale.LOCAL,
        visibility=ConsequenceVisibility.HIDDEN,
        trigger=ConsequenceTrigger.immediate(),
        effect=ConsequenceEffect.INFORMATIONAL_LEARN,
        payload={
            "npc_id": str(next(npc.id for npc in world_engine.get_npcs(instance.id) if npc.key == "caretaker")),
            "information_key": "damaged_radio",
        },
    )
    assert applied.ok is True, applied.error
    consequence_id = ConsequenceId(applied.payload["consequence_id"])

    result = world_engine.cancel_consequence(instance.id, consequence_id)

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.INVALID_ACTION
    assert world_engine.get_consequence(instance.id, consequence_id).status is ConsequenceStatus.APPLIED


def test_transform_consequence_creates_events_and_repeat_is_noop(
    world_engine: WorldEngine,
) -> None:
    instance = make_world(world_engine)
    consequence_id = schedule_pending(world_engine, instance)
    event_count = len(world_engine.get_events(instance.id))
    replacement = {
        "type": ConsequenceType.INFORMATIONAL,
        "scale": ConsequenceScale.REGIONAL,
        "visibility": ConsequenceVisibility.HIDDEN,
        "trigger": ConsequenceTrigger.after_ticks(200),
        "effect": ConsequenceEffect.INFORMATIONAL_LEARN,
        "payload": dict(world_engine.get_consequence(instance.id, consequence_id).payload),
    }

    transformed = world_engine.transform_consequence(
        instance.id, consequence_id, **replacement
    )

    assert transformed.ok is True, transformed.error
    assert len(world_engine.get_events(instance.id)) == event_count + 2
    assert [event.type for event in world_engine.get_events(instance.id)[-2:]] == [
        EventType.CONSEQUENCE_TRANSFORMED,
        EventType.CONSEQUENCE_CREATED,
    ]
    assert world_engine.get_consequence(instance.id, consequence_id).status is (
        ConsequenceStatus.TRANSFORMED
    )
    replacement_id = ConsequenceId(transformed.payload["transformed_to"])
    assert world_engine.get_consequence(instance.id, replacement_id).status is (
        ConsequenceStatus.PENDING
    )

    repeated = world_engine.transform_consequence(
        instance.id, consequence_id, **replacement
    )
    assert repeated.ok is True, repeated.error
    assert repeated.payload["already_transformed"] is True
    assert len(world_engine.get_events(instance.id)) == event_count + 2


def test_transform_from_another_instance_is_isolated(world_engine: WorldEngine) -> None:
    world_one = make_world(world_engine, -1001)
    world_two = make_world(world_engine, -1002)
    consequence_id = schedule_pending(world_engine, world_one)
    events_two = len(world_engine.get_events(world_two.id))

    result = world_engine.cancel_consequence(world_two.id, consequence_id)

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_FOUND
    assert len(world_engine.get_events(world_two.id)) == events_two
    assert world_engine.get_consequence(world_one.id, consequence_id).status is (
        ConsequenceStatus.PENDING
    )
