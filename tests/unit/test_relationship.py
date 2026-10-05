"""Unit: отношения — лестницы, guard'ы, шаги и значимые действия."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from world_error.domain.events.event import Event, EventType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipDirection,
    RelationshipKind,
    RelationshipVisibility,
    SubjectRef,
    MembershipLevel,
    StandingLevel,
    SuspicionLevel,
    TrustLevel,
    baseline_level,
    level_index,
    step_level,
)
from world_error.domain.relationships.rules import (
    SignificantAction,
    effects_of,
    is_source_distrusted,
)
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    EventId,
    RelationshipId,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
OTHER_WORLD_ID = WorldInstanceId("wi_other")
NPC = SubjectRef(type=SubjectType.NPC, id="npc_caretaker")
CHARACTER = SubjectRef(type=SubjectType.CHARACTER, id="ch_anna")
FACTION = SubjectRef(type=SubjectType.FACTION, id="fac_expedition")
OTHER_FACTION = SubjectRef(type=SubjectType.FACTION, id="fac_union")


def make_relationship(
    *,
    kind: RelationshipKind = RelationshipKind.TRUST,
    holder: SubjectRef = NPC,
    subject: SubjectRef = CHARACTER,
    holder_instance_id: WorldInstanceId = WORLD_ID,
    subject_instance_id: WorldInstanceId = WORLD_ID,
) -> Relationship:
    return Relationship.create(
        id=RelationshipId("rel_1"),
        holder=holder,
        holder_instance_id=holder_instance_id,
        subject=subject,
        subject_instance_id=subject_instance_id,
        kind=kind,
        now=NOW,
    )


def make_event(
    changes: list[dict[str, str]],
    *,
    holder: SubjectRef = NPC,
    subject: SubjectRef = CHARACTER,
    event_type: EventType = EventType.RELATIONSHIP_CHANGED,
    world_instance_id: WorldInstanceId = WORLD_ID,
) -> Event:
    return Event(
        id=EventId("ev_rel"),
        world_instance_id=world_instance_id,
        type=event_type,
        created_at=NOW,
        executed_at=NOW,
        actor=holder.id,
        target=subject.id,
        payload={
            "holder_type": holder.type.value,
            "holder_id": holder.id,
            "subject_type": subject.type.value,
            "subject_id": subject.id,
            "reason": "TEST",
            "changes": changes,
        },
    )


# --- лестницы --------------------------------------------------------------


def test_baselines_are_named_levels() -> None:
    assert baseline_level(RelationshipKind.TRUST) is TrustLevel.NEUTRAL
    assert baseline_level(RelationshipKind.SUSPICION) is SuspicionLevel.NONE


def test_trust_ladder_order() -> None:
    assert level_index(RelationshipKind.TRUST, TrustLevel.HOSTILE) == 0
    assert level_index(RelationshipKind.TRUST, TrustLevel.DEVOTED) == 4


def test_suspicion_ladder_order() -> None:
    assert level_index(RelationshipKind.SUSPICION, SuspicionLevel.NONE) == 0
    assert level_index(RelationshipKind.SUSPICION, SuspicionLevel.HIGH) == 3


def test_standing_and_membership_have_independent_baselines_and_ladders() -> None:
    assert baseline_level(RelationshipKind.STANDING).value == "NEUTRAL"
    assert level_index(RelationshipKind.STANDING, "ALLIED") == 0
    assert level_index(RelationshipKind.STANDING, "AT_WAR") == 5
    assert baseline_level(RelationshipKind.MEMBERSHIP).value == "OUTSIDER"
    assert level_index(RelationshipKind.MEMBERSHIP, "OFFICER") == 3


def test_step_moves_exactly_one_level() -> None:
    assert step_level(RelationshipKind.TRUST, TrustLevel.NEUTRAL, RelationshipDirection.INCREASE) is TrustLevel.FRIENDLY
    assert step_level(RelationshipKind.TRUST, TrustLevel.NEUTRAL, RelationshipDirection.DECREASE) is TrustLevel.WARY
    assert step_level(RelationshipKind.SUSPICION, SuspicionLevel.LOW, RelationshipDirection.INCREASE) is SuspicionLevel.MEDIUM


def test_step_clamps_at_ladder_edges() -> None:
    assert step_level(RelationshipKind.TRUST, TrustLevel.HOSTILE, RelationshipDirection.DECREASE) is None
    assert step_level(RelationshipKind.TRUST, TrustLevel.DEVOTED, RelationshipDirection.INCREASE) is None
    assert step_level(RelationshipKind.SUSPICION, SuspicionLevel.NONE, RelationshipDirection.DECREASE) is None
    assert step_level(RelationshipKind.SUSPICION, SuspicionLevel.HIGH, RelationshipDirection.INCREASE) is None


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(DomainError) as exc_info:
        level_index(RelationshipKind.TRUST, "SHINY")
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


# --- создание --------------------------------------------------------------


def test_created_relationship_uses_baseline() -> None:
    relationship = make_relationship()
    assert relationship.level is TrustLevel.NEUTRAL
    assert relationship.holder == NPC
    assert relationship.subject == CHARACTER


def test_relationship_visibility_defaults_public() -> None:
    relationship = make_relationship(kind=RelationshipKind.STANDING, holder=FACTION, subject=OTHER_FACTION)
    assert relationship.visibility is RelationshipVisibility.PUBLIC


def test_relationship_with_itself_is_rejected() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_relationship(subject=NPC)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_relationship_across_instances_is_rejected() -> None:
    with pytest.raises(DomainError) as exc_info:
        make_relationship(subject_instance_id=OTHER_WORLD_ID)
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_faction_subject_is_supported_for_standing_and_membership() -> None:
    faction = SubjectRef(type=SubjectType.FACTION, id="fac_one")
    other_faction = SubjectRef(type=SubjectType.FACTION, id="fac_two")
    standing = make_relationship(
        kind=RelationshipKind.STANDING, holder=faction, subject=other_faction
    )
    membership = make_relationship(
        kind=RelationshipKind.MEMBERSHIP, holder=faction, subject=CHARACTER
    )

    assert standing.level is StandingLevel.NEUTRAL
    assert membership.level is MembershipLevel.OUTSIDER
    with pytest.raises(DomainError) as exc_info:
        make_relationship(kind=RelationshipKind.MEMBERSHIP, holder=faction, subject=NPC)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


# --- применение события ----------------------------------------------------


def test_event_moves_level_one_step() -> None:
    relationship = make_relationship()
    relationship.apply(
        make_event([{"kind": "TRUST", "from": "NEUTRAL", "to": "FRIENDLY"}])
    )
    assert relationship.level is TrustLevel.FRIENDLY
    assert relationship.updated_at == NOW


def test_standing_event_can_change_level_and_visibility_together() -> None:
    relationship = make_relationship(
        kind=RelationshipKind.STANDING, holder=FACTION, subject=OTHER_FACTION
    )
    event = make_event(
        [{"kind": "STANDING", "from": "NEUTRAL", "to": "COMPETITIVE"}],
        holder=FACTION,
        subject=OTHER_FACTION,
    )
    event = Event(
        id=event.id,
        world_instance_id=event.world_instance_id,
        type=event.type,
        created_at=event.created_at,
        executed_at=event.executed_at,
        actor=event.actor,
        target=event.target,
        payload={**event.payload, "visibility": "SECRET"},
    )

    relationship.apply(event)

    assert relationship.level.value == "COMPETITIVE"
    assert relationship.visibility is RelationshipVisibility.SECRET


def test_visibility_can_change_without_moving_past_ladder_edge() -> None:
    relationship = make_relationship(
        kind=RelationshipKind.STANDING, holder=FACTION, subject=OTHER_FACTION
    )
    relationship.level = StandingLevel.AT_WAR
    event = make_event(
        [{"kind": "STANDING", "from": "AT_WAR", "to": "AT_WAR"}],
        holder=FACTION,
        subject=OTHER_FACTION,
    )
    event = Event(
        id=event.id,
        world_instance_id=event.world_instance_id,
        type=event.type,
        created_at=event.created_at,
        executed_at=event.executed_at,
        actor=event.actor,
        target=event.target,
        payload={**event.payload, "visibility": "SECRET"},
    )

    relationship.apply(event)

    assert relationship.level is StandingLevel.AT_WAR
    assert relationship.visibility is RelationshipVisibility.SECRET


def test_event_skipping_levels_is_rejected() -> None:
    relationship = make_relationship()
    with pytest.raises(DomainError) as exc_info:
        relationship.apply(
            make_event([{"kind": "TRUST", "from": "NEUTRAL", "to": "DEVOTED"}])
        )
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
    assert relationship.level is TrustLevel.NEUTRAL


def test_event_for_another_kind_does_not_change_this_row() -> None:
    relationship = make_relationship()
    relationship.apply(
        make_event([{"kind": "SUSPICION", "from": "NONE", "to": "LOW"}])
    )
    assert relationship.level is TrustLevel.NEUTRAL


def test_event_for_another_pair_is_rejected() -> None:
    relationship = make_relationship()
    other = SubjectRef(type=SubjectType.CHARACTER, id="ch_boris")
    with pytest.raises(DomainError) as exc_info:
        relationship.apply(
            make_event([{"kind": "TRUST", "from": "NEUTRAL", "to": "FRIENDLY"}], subject=other)
        )
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_event_from_another_instance_is_rejected() -> None:
    relationship = make_relationship()
    with pytest.raises(DomainError) as exc_info:
        relationship.apply(
            make_event(
                [{"kind": "TRUST", "from": "NEUTRAL", "to": "FRIENDLY"}],
                world_instance_id=OTHER_WORLD_ID,
            )
        )
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_unsupported_event_type_is_rejected() -> None:
    relationship = make_relationship()
    with pytest.raises(DomainError) as exc_info:
        relationship.apply(
            make_event(
                [{"kind": "TRUST", "from": "NEUTRAL", "to": "FRIENDLY"}],
                event_type=EventType.NPC_LEARNED,
            )
        )
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


# --- значимые действия -----------------------------------------------------


def test_significant_action_effects() -> None:
    assert effects_of(SignificantAction.HELPED) == (
        (RelationshipKind.TRUST, RelationshipDirection.INCREASE),
    )
    for action in (SignificantAction.BETRAYED, SignificantAction.LIED_TO):
        assert effects_of(action) == (
            (RelationshipKind.TRUST, RelationshipDirection.DECREASE),
            (RelationshipKind.SUSPICION, RelationshipDirection.INCREASE),
        )


def test_distrust_gate_levels() -> None:
    assert is_source_distrusted(trust_level=TrustLevel.HOSTILE, suspicion_level=None) is True
    assert is_source_distrusted(trust_level=None, suspicion_level=SuspicionLevel.HIGH) is True
    assert is_source_distrusted(trust_level=TrustLevel.NEUTRAL, suspicion_level=SuspicionLevel.NONE) is False
    assert is_source_distrusted(trust_level=TrustLevel.WARY, suspicion_level=SuspicionLevel.MEDIUM) is False
    assert is_source_distrusted(trust_level=None, suspicion_level=None) is False
