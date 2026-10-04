"""Unit: сущность последствия, триггеры, словарь и правила."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from world_error.domain.consequences.consequence import (
    Consequence,
    ConsequenceCause,
    ConsequenceTrigger,
    origin_of,
)
from world_error.domain.consequences.rules import ConsequenceRule
from world_error.domain.consequences.vocabulary import (
    CauseOrigin,
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceStatus,
    ConsequenceType,
    ConsequenceVisibility,
    TriggerKind,
    effect_type_of,
    event_type_for,
    is_self_triggering,
)
from world_error.domain.events.event import Event, EventType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    ConsequenceId,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
CAUSE = ConsequenceCause(event_id=EventId("ev_cause"), origin=CauseOrigin.ACTOR)
INFORMATIONAL_PAYLOAD = {"npc_id": "npc_caretaker", "information_key": "damaged_radio"}


def make_consequence(**overrides) -> Consequence:
    params = {
        "id": ConsequenceId("csq_1"),
        "world_instance_id": WORLD_ID,
        "causes": (CAUSE,),
        "type": ConsequenceType.INFORMATIONAL,
        "scale": ConsequenceScale.LOCAL,
        "visibility": ConsequenceVisibility.HIDDEN,
        "trigger": ConsequenceTrigger.immediate(),
        "effect": ConsequenceEffect.INFORMATIONAL_LEARN,
        "payload": dict(INFORMATIONAL_PAYLOAD),
        "created_tick": 7,
        "now": NOW,
    }
    params.update(overrides)
    return Consequence.create(**params)  # type: ignore[arg-type]


# --- триггеры --------------------------------------------------------------


def test_immediate_trigger_has_no_parameters() -> None:
    trigger = ConsequenceTrigger.immediate()
    assert trigger.kind is TriggerKind.IMMEDIATE
    assert trigger.due_tick(created_tick=5) == 5
    assert trigger.tick_is_due(current_tick=5, due_tick=5) is True


def test_immediate_trigger_rejects_parameters() -> None:
    with pytest.raises(DomainError) as exc_info:
        ConsequenceTrigger(kind=TriggerKind.IMMEDIATE, delay_ticks=1)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_after_ticks_requires_positive_delay() -> None:
    with pytest.raises(DomainError) as exc_info:
        ConsequenceTrigger.after_ticks(0)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_after_ticks_waits_for_its_tick() -> None:
    trigger = ConsequenceTrigger.after_ticks(3)
    assert trigger.due_tick(created_tick=10) == 13
    assert trigger.tick_is_due(current_tick=12, due_tick=13) is False
    assert trigger.tick_is_due(current_tick=13, due_tick=13) is True


def test_on_event_type_requires_event_type() -> None:
    with pytest.raises(DomainError) as exc_info:
        ConsequenceTrigger(kind=TriggerKind.ON_EVENT_TYPE)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_on_event_type_is_not_tick_driven() -> None:
    trigger = ConsequenceTrigger.on_event_type(EventType.NPC_LEARNED)
    assert trigger.waits_for_event is True
    assert trigger.due_tick(created_tick=4) == 4
    assert trigger.tick_is_due(current_tick=999, due_tick=4) is False


# --- сущность --------------------------------------------------------------


def test_consequence_without_cause_is_rejected() -> None:
    """§14: последствие без причины не существует."""
    with pytest.raises(DomainError) as exc_info:
        make_consequence(causes=())
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_duplicate_causes_are_rejected() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_consequence(causes=(CAUSE, CAUSE))
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_type_must_match_effect() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_consequence(type=ConsequenceType.PHYSICAL)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_effect_payload_is_validated() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_consequence(payload={"npc_id": "npc_caretaker"})
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_relational_payload_rejects_faction() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_consequence(
            type=ConsequenceType.RELATIONAL,
            effect=ConsequenceEffect.RELATIONAL_SHIFT,
            payload={
                "holder_type": SubjectType.FACTION.value,
                "holder_id": "faction_1",
                "subject_type": SubjectType.NPC.value,
                "subject_id": "npc_scout",
                "kind": "TRUST",
                "direction": "DECREASE",
            },
        )
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_self_triggering_consequence_is_rejected() -> None:
    """M3: последствие не может запускаться событием, которое само порождает."""
    with pytest.raises(DomainError) as exc_info:
        make_consequence(trigger=ConsequenceTrigger.on_event_type(EventType.NPC_LEARNED))
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
    assert is_self_triggering(
        ConsequenceTrigger.on_event_type(event_type_for(ConsequenceEffect.INFORMATIONAL_LEARN)),
        ConsequenceEffect.INFORMATIONAL_LEARN,
    )


def test_consequence_keeps_first_cause_as_source() -> None:
    second = ConsequenceCause(event_id=EventId("ev_second"), origin=CauseOrigin.WORLD)
    consequence = make_consequence(causes=(CAUSE, second))
    assert consequence.source_event_id == CAUSE.event_id
    assert consequence.has_cause(EventId("ev_second")) is True
    assert len(consequence.causes) == 2


def test_status_transitions_are_idempotent() -> None:
    consequence = make_consequence()
    assert consequence.can_apply() is True
    assert consequence.mark_applied(event_id=EventId("ev_effect"), now=NOW) is True
    assert consequence.status is ConsequenceStatus.APPLIED
    assert consequence.mark_applied(event_id=EventId("ev_later"), now=NOW) is False
    assert consequence.applied_event_id == EventId("ev_effect")
    assert consequence.mark_failed(now=NOW) is False

    failed = make_consequence()
    assert failed.mark_failed(now=NOW) is True
    assert failed.status is ConsequenceStatus.FAILED
    with pytest.raises(DomainError) as exc_info:
        failed.ensure_can_apply()
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_cancel_and_transform_only_close_pending_consequences() -> None:
    cancelled = make_consequence()
    assert cancelled.cancel(now=NOW) is True
    assert cancelled.status is ConsequenceStatus.CANCELLED
    assert cancelled.cancel(now=NOW) is False
    with pytest.raises(DomainError) as exc_info:
        cancelled.mark_transformed(now=NOW)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION

    transformed = make_consequence()
    assert transformed.mark_transformed(now=NOW) is True
    assert transformed.status is ConsequenceStatus.TRANSFORMED
    assert transformed.mark_transformed(now=NOW) is False
    with pytest.raises(DomainError) as exc_info:
        transformed.cancel(now=NOW)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION

    applied = make_consequence()
    applied.mark_applied(event_id=EventId("ev_applied"), now=NOW)
    with pytest.raises(DomainError) as exc_info:
        applied.cancel(now=NOW)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
    with pytest.raises(DomainError) as exc_info:
        applied.mark_transformed(now=NOW)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


# --- происхождение (M10) ---------------------------------------------------


def make_event(*, actor=None, cause=None) -> Event:  # noqa: ANN001
    return Event(
        id=EventId("ev_x"),
        world_instance_id=WORLD_ID,
        type=EventType.CHARACTER_CREATED,
        created_at=NOW,
        actor=actor,
        cause=cause,
    )


def test_origin_is_actor_when_event_has_actor() -> None:
    assert origin_of(make_event(actor="ch_anna")) is CauseOrigin.ACTOR


def test_origin_is_world_when_event_has_no_actor() -> None:
    assert origin_of(make_event()) is CauseOrigin.WORLD


def test_origin_is_world_for_engine_generated_events() -> None:
    """Синтетический actor движка — не субъект мира."""
    assert origin_of(make_event(actor="system")) is CauseOrigin.WORLD


def test_origin_is_consequence_for_effect_events() -> None:
    assert (
        origin_of(make_event(actor="npc_1", cause="consequence:csq_1"))
        is CauseOrigin.CONSEQUENCE
    )


# --- словарь ---------------------------------------------------------------


def test_effect_event_and_type_mapping() -> None:
    assert event_type_for(ConsequenceEffect.INFORMATIONAL_LEARN) is EventType.NPC_LEARNED
    assert event_type_for(ConsequenceEffect.RELATIONAL_SHIFT) is EventType.RELATIONSHIP_CHANGED
    assert event_type_for(ConsequenceEffect.PHYSICAL_STATUS_CHANGE) is EventType.NPC_STATUS_CHANGED
    assert event_type_for(ConsequenceEffect.PHYSICAL_RELOCATE) is EventType.NPC_MOVED
    assert effect_type_of(ConsequenceEffect.PHYSICAL_RELOCATE) is ConsequenceType.PHYSICAL


def test_scale_and_visibility_sets_are_canonical() -> None:
    assert {item.value for item in ConsequenceScale} == {
        "PERSONAL",
        "LOCAL",
        "REGIONAL",
        "GLOBAL",
    }
    assert {item.value for item in ConsequenceVisibility} == {
        "VISIBLE",
        "PARTIALLY_VISIBLE",
        "HIDDEN",
        "INDIRECT",
        "UNKNOWN",
    }


# --- правила ---------------------------------------------------------------


def make_rule(**overrides) -> ConsequenceRule:
    params = {
        "key": "radio_rumor",
        "on_event_type": EventType.INFORMATION_DISCOVERED,
        "when_payload": {"information_key": "damaged_radio"},
        "type": ConsequenceType.INFORMATIONAL,
        "scale": ConsequenceScale.LOCAL,
        "visibility": ConsequenceVisibility.HIDDEN,
        "trigger": ConsequenceTrigger.after_ticks(2),
        "effect": ConsequenceEffect.INFORMATIONAL_LEARN,
        "effect_keys": {"npc_key": "mechanic", "information_key": "damaged_radio"},
    }
    params.update(overrides)
    return ConsequenceRule(**params)  # type: ignore[arg-type]


def test_rule_matches_event_type_and_payload() -> None:
    rule = make_rule()
    matching = Event(
        id=EventId("ev_1"),
        world_instance_id=WORLD_ID,
        type=EventType.INFORMATION_DISCOVERED,
        created_at=NOW,
        payload={"information_key": "damaged_radio"},
    )
    other_payload = Event(
        id=EventId("ev_2"),
        world_instance_id=WORLD_ID,
        type=EventType.INFORMATION_DISCOVERED,
        created_at=NOW,
        payload={"information_key": "other"},
    )
    other_type = Event(
        id=EventId("ev_3"),
        world_instance_id=WORLD_ID,
        type=EventType.KNOWLEDGE_SHARED,
        created_at=NOW,
        payload={"information_key": "damaged_radio"},
    )
    assert rule.matches(matching) is True
    assert rule.matches(other_payload) is False
    assert rule.matches(other_type) is False


def test_rule_requires_when_payload() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_rule(when_payload={})
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_rule_rejects_self_triggering_pair() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_rule(trigger=ConsequenceTrigger.on_event_type(EventType.NPC_LEARNED))
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_rule_requires_effect_keys() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_rule(effect_keys={"npc_key": "mechanic"})
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
