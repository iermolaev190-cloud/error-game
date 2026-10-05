"""Scenario: factions and membership share the world event loop."""

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.factions.faction import FactionStatus
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import (
    MembershipLevel,
    RelationshipDirection,
    RelationshipKind,
    StandingLevel,
    SubjectRef,
)


def test_faction_membership_and_standing_use_shared_events(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1020, seed=20)
    factions = {faction.key: faction for faction in world_engine.get_factions(instance.id)}
    expedition = SubjectRef(type=SubjectType.FACTION, id=str(factions["expedition"].id))
    union = SubjectRef(type=SubjectType.FACTION, id=str(factions["union"].id))
    character_result = world_engine.create_character(
        instance.id, player_id="worker", name="Worker"
    )
    character = SubjectRef(
        type=SubjectType.CHARACTER,
        id=character_result.payload["character_id"],
    )

    standing = world_engine.change_relationship(
        instance.id,
        holder=expedition,
        subject=union,
        kind=RelationshipKind.STANDING,
        direction=RelationshipDirection.INCREASE,
    )
    member = world_engine.change_relationship(
        instance.id,
        holder=expedition,
        subject=character,
        kind=RelationshipKind.MEMBERSHIP,
        direction=RelationshipDirection.INCREASE,
    )
    status = world_engine.change_faction_status(
        instance.id,
        faction_id=factions["expedition"].id,
        to_status=FactionStatus.CONFLICT,
    )

    assert standing.ok and member.ok and status.ok
    standing_record = world_engine.get_relationship(
        instance.id, holder=expedition, subject=union, kind=RelationshipKind.STANDING
    )
    membership_record = world_engine.get_relationship(
        instance.id, holder=expedition, subject=character, kind=RelationshipKind.MEMBERSHIP
    )
    assert standing_record is not None and standing_record.level is StandingLevel.COMPETITIVE
    assert membership_record is not None and membership_record.level is MembershipLevel.SYMPATHISER
    assert [event.type for event in world_engine.get_events(instance.id)].count(
        EventType.FACTION_STATUS_CHANGED
    ) == 1
    assert sum(
        event.type is EventType.RELATIONSHIP_CHANGED for event in world_engine.get_events(instance.id)
    ) == 2
    assert world_engine.get_instance(instance.id).state.state_version == 4