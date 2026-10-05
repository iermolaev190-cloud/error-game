"""Сопоставление доменных объектов и строк БД."""

from __future__ import annotations

from datetime import datetime, timezone

from world_error.domain.characters.character import (
    Character,
    CharacterActivity,
    CharacterLifecycle,
)
from world_error.domain.consequences.consequence import (
    Consequence,
    ConsequenceCause,
    ConsequenceTrigger,
)
from world_error.domain.consequences.vocabulary import (
    CauseOrigin,
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceStatus,
    ConsequenceType,
    ConsequenceVisibility,
    TriggerKind,
)
from world_error.domain.events.event import Event, EventType
from world_error.domain.factions.faction import Faction, FactionStatus
from world_error.domain.information.information import Information
from world_error.domain.items.item import Item, ItemOwnerType
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.locations.location import LocationState
from world_error.domain.legacy.legacy_document import LegacyDocument
from world_error.domain.npcs.npc import Npc, NpcStatus
from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipKind,
    RelationshipVisibility,
    SubjectRef,
    coerce_level,
)
from world_error.domain.shared.kernel import (
    CharacterId,
    ConsequenceId,
    DiscoveryState,
    EventId,
    FactionId,
    InformationId,
    ItemId,
    KnowledgeId,
    LocationKey,
    LegacyDocumentId,
    NpcId,
    RelationshipId,
    ScheduledEventId,
    WorldInstanceId,
)
from world_error.domain.time.scheduled_event import (
    ScheduledEvent,
    ScheduledEventStatus,
    ScheduledEventTrigger,
    ScheduledTriggerKind,
)
from world_error.domain.world.instance import (
    InstanceEnvironment,
    InstanceLifecycle,
    WorldInstance,
    WorldState,
)


def as_utc(value: datetime) -> datetime:
    """SQLite не хранит tzinfo: возвращаем время как UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def as_utc_optional(value: datetime | None) -> datetime | None:
    return None if value is None else as_utc(value)


# --- world instance -------------------------------------------------------


def instance_row(instance: WorldInstance) -> dict[str, object]:
    return {
        "id": str(instance.id),
        "telegram_chat_id": instance.telegram_chat_id,
        "seed": instance.seed,
        "content_version": instance.content_version,
        "environment": instance.environment.value,
        "lifecycle": instance.lifecycle.value,
        "current_time": instance.state.current_time,
        "anchor_real_time": instance.anchor_real_time,
        "time_scale": instance.time_scale,
        "world_tick": instance.state.world_tick,
        "state_version": instance.state.state_version,
        "created_at": instance.created_at,
    }


def instance_from_row(row: dict) -> WorldInstance:
    return WorldInstance(
        id=WorldInstanceId(row["id"]),
        telegram_chat_id=row["telegram_chat_id"],
        seed=row["seed"],
        content_version=row["content_version"],
        environment=InstanceEnvironment(row["environment"]),
        lifecycle=InstanceLifecycle(row["lifecycle"]),
        created_at=as_utc(row["created_at"]),
        state=WorldState(
            current_time=as_utc(row["current_time"]),
            world_tick=row["world_tick"],
            state_version=row["state_version"],
        ),
        anchor_real_time=as_utc(row["anchor_real_time"]),
        time_scale=row["time_scale"],
    )


# --- event ----------------------------------------------------------------


def event_row(event: Event) -> dict[str, object]:
    return {
        "id": str(event.id),
        "world_instance_id": str(event.world_instance_id),
        "type": event.type.value,
        "actor": event.actor,
        "target": event.target,
        "cause": event.cause,
        "payload": dict(event.payload),
        "metadata": dict(event.metadata),
        "created_at": event.created_at,
        "executed_at": event.executed_at,
        "result": event.result,
    }


def event_from_row(row: dict) -> Event:
    return Event(
        id=EventId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        type=EventType(row["type"]),
        created_at=as_utc(row["created_at"]),
        actor=row["actor"],
        target=row["target"],
        cause=row["cause"],
        payload=dict(row["payload"] or {}),
        executed_at=as_utc_optional(row["executed_at"]),
        result=row["result"],
        metadata=dict(row["metadata"] or {}),
    )


def scheduled_event_row(item: ScheduledEvent) -> dict[str, object]:
    return {
        "id": str(item.id),
        "world_instance_id": str(item.world_instance_id),
        "cause_event_id": str(item.cause_event_id),
        "created_event_id": str(item.created_event_id),
        "trigger_kind": item.trigger.kind.value,
        "due_tick": item.trigger.due_tick,
        "due_time": item.trigger.due_time,
        "trigger_event_type": (
            None if item.trigger.event_type is None else item.trigger.event_type.value
        ),
        "event_key": item.event_key,
        "idempotency_key": item.idempotency_key,
        "payload": dict(item.payload),
        "metadata": dict(item.metadata),
        "status": item.status.value,
        "created_at": item.created_at,
        "applied_at": item.applied_at,
        "triggered_event_id": (
            None if item.triggered_event_id is None else str(item.triggered_event_id)
        ),
    }


def scheduled_event_from_row(row: dict) -> ScheduledEvent:
    return ScheduledEvent(
        id=ScheduledEventId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        cause_event_id=EventId(row["cause_event_id"]),
        created_event_id=EventId(row["created_event_id"]),
        idempotency_key=row["idempotency_key"],
        trigger=ScheduledEventTrigger(
            kind=ScheduledTriggerKind(row["trigger_kind"]),
            due_tick=row["due_tick"],
            due_time=as_utc_optional(row["due_time"]),
            event_type=(
                None
                if row["trigger_event_type"] is None
                else EventType(row["trigger_event_type"])
            ),
        ),
        event_key=row["event_key"],
        payload=dict(row["payload"] or {}),
        created_at=as_utc(row["created_at"]),
        status=ScheduledEventStatus(row["status"]),
        triggered_event_id=(
            None if row["triggered_event_id"] is None else EventId(row["triggered_event_id"])
        ),
        applied_at=as_utc_optional(row["applied_at"]),
        metadata=dict(row["metadata"] or {}),
    )


def legacy_document_row(document: LegacyDocument) -> dict[str, object]:
    return {
        "id": str(document.id),
        "world_instance_id": str(document.world_instance_id),
        "document_key": document.document_key,
        "location_key": str(document.location_key),
        "created_by_character_id": str(document.created_by_character_id),
        "death_event_id": str(document.death_event_id),
        "created_event_id": str(document.created_event_id),
        "content": document.content,
        "created_at": document.created_at,
    }


def legacy_document_from_row(row: dict) -> LegacyDocument:
    return LegacyDocument(
        id=LegacyDocumentId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        document_key=row["document_key"],
        location_key=LocationKey(row["location_key"]),
        created_by_character_id=CharacterId(row["created_by_character_id"]),
        death_event_id=EventId(row["death_event_id"]),
        created_event_id=EventId(row["created_event_id"]),
        content=row["content"],
        created_at=as_utc(row["created_at"]),
    )


# --- character ------------------------------------------------------------


def character_row(character: Character) -> dict[str, object]:
    return {
        "id": str(character.id),
        "world_instance_id": str(character.world_instance_id),
        "player_id": character.player_id,
        "name": character.name,
        "lifecycle": character.lifecycle.value,
        "activity": character.activity.value,
        "location_key": str(character.location_key),
        "created_at": character.created_at,
        "updated_at": character.updated_at,
        "death_event_id": None if character.death_event_id is None else str(character.death_event_id),
        "death_cause_event_id": (
            None if character.death_cause_event_id is None else str(character.death_cause_event_id)
        ),
    }


def character_from_row(row: dict) -> Character:
    return Character(
        id=CharacterId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        player_id=row["player_id"],
        name=row["name"],
        lifecycle=CharacterLifecycle(row["lifecycle"]),
        activity=CharacterActivity(row["activity"]),
        location_key=LocationKey(row["location_key"]),
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
        death_event_id=(
            None if row["death_event_id"] is None else EventId(row["death_event_id"])
        ),
        death_cause_event_id=(
            None if row["death_cause_event_id"] is None else EventId(row["death_cause_event_id"])
        ),
    )


# --- location state -------------------------------------------------------


def location_row(state: LocationState) -> dict[str, object]:
    return {
        "world_instance_id": str(state.world_instance_id),
        "key": str(state.key),
        "discovery_state": state.discovery_state.value,
        "first_visited_at": state.first_visited_at,
        "updated_at": state.updated_at,
    }


def location_from_row(row: dict) -> LocationState:
    return LocationState(
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        key=LocationKey(row["key"]),
        updated_at=as_utc(row["updated_at"]),
        discovery_state=DiscoveryState(row["discovery_state"]),
        first_visited_at=as_utc_optional(row["first_visited_at"]),
    )


# --- information ----------------------------------------------------------


def information_row(information: Information) -> dict[str, object]:
    return {
        "id": str(information.id),
        "world_instance_id": str(information.world_instance_id),
        "key": information.key,
        "location_key": str(information.location_key),
        "discovery_state": information.discovery_state.value,
        "discovered_by": str(information.discovered_by) if information.discovered_by else None,
        "discovered_at": information.discovered_at,
        "created_at": information.created_at,
    }


def information_from_row(row: dict) -> Information:
    return Information(
        id=InformationId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        key=row["key"],
        location_key=LocationKey(row["location_key"]),
        discovery_state=DiscoveryState(row["discovery_state"]),
        discovered_by=row["discovered_by"],
        discovered_at=as_utc_optional(row["discovered_at"]),
        created_at=as_utc_optional(row["created_at"]),
    )


# --- knowledge ------------------------------------------------------------


def knowledge_row(knowledge: Knowledge) -> dict[str, object]:
    return {
        "id": str(knowledge.id),
        "world_instance_id": str(knowledge.world_instance_id),
        "subject_type": knowledge.subject_type.value,
        "subject_id": knowledge.subject_id,
        "information_id": str(knowledge.information_id),
        "claim": knowledge.claim,
        "claim_type": knowledge.claim_type.value,
        "source": knowledge.source.value,
        "source_ref": knowledge.source_ref,
        "confidence": knowledge.confidence.value,
        "acquired_at": knowledge.acquired_at,
        "document_date": knowledge.document_date,
    }


def knowledge_from_row(row: dict) -> Knowledge:
    return Knowledge(
        id=KnowledgeId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        subject_type=SubjectType(row["subject_type"]),
        subject_id=row["subject_id"],
        information_id=InformationId(row["information_id"]),
        claim=row["claim"],
        claim_type=ClaimType(row["claim_type"]),
        source=KnowledgeSource(row["source"]),
        source_ref=row["source_ref"],
        confidence=KnowledgeConfidence(row["confidence"]),
        acquired_at=as_utc(row["acquired_at"]),
        document_date=row["document_date"],
    )


# --- npc ------------------------------------------------------------------


def npc_row(npc: Npc) -> dict[str, object]:
    return {
        "id": str(npc.id),
        "world_instance_id": str(npc.world_instance_id),
        "key": npc.key,
        "location_key": str(npc.location_key),
        "status": npc.status.value,
        "created_at": npc.created_at,
        "updated_at": npc.updated_at,
    }


def npc_from_row(row: dict) -> Npc:
    return Npc(
        id=NpcId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        key=row["key"],
        location_key=LocationKey(row["location_key"]),
        status=NpcStatus(row["status"]),
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )


# --- faction --------------------------------------------------------------


def faction_row(faction: Faction) -> dict[str, object]:
    return {
        "id": str(faction.id),
        "world_instance_id": str(faction.world_instance_id),
        "key": faction.key,
        "status": faction.status.value,
        "created_at": faction.created_at,
        "updated_at": faction.updated_at,
    }


def faction_from_row(row: dict, location_keys: tuple[LocationKey, ...] = ()) -> Faction:
    return Faction(
        id=FactionId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        key=row["key"],
        status=FactionStatus(row["status"]),
        location_keys=location_keys,
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )


# --- item -----------------------------------------------------------------


def item_row(item: Item) -> dict[str, object]:
    return {
        "id": str(item.id),
        "world_instance_id": str(item.world_instance_id),
        "key": item.key,
        "owner_type": item.owner_type.value,
        "owner_id": item.owner_id,
        "location_key": None if item.location_key is None else str(item.location_key),
        "quantity": item.quantity,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def item_from_row(row: dict) -> Item:
    return Item(
        id=ItemId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        key=row["key"],
        owner_type=ItemOwnerType(row["owner_type"]),
        owner_id=row["owner_id"],
        location_key=(None if row["location_key"] is None else LocationKey(row["location_key"])),
        quantity=row["quantity"],
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )


# --- relationship ---------------------------------------------------------


def relationship_row(relationship: Relationship) -> dict[str, object]:
    return {
        "id": str(relationship.id),
        "world_instance_id": str(relationship.world_instance_id),
        "holder_type": relationship.holder.type.value,
        "holder_id": relationship.holder.id,
        "subject_type": relationship.subject.type.value,
        "subject_id": relationship.subject.id,
        "kind": relationship.kind.value,
        "level": relationship.level.value,
        "visibility": relationship.visibility.value,
        "created_at": relationship.created_at,
        "updated_at": relationship.updated_at,
    }


def relationship_from_row(row: dict) -> Relationship:
    kind = RelationshipKind(row["kind"])
    return Relationship(
        id=RelationshipId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        holder=SubjectRef(type=SubjectType(row["holder_type"]), id=row["holder_id"]),
        subject=SubjectRef(type=SubjectType(row["subject_type"]), id=row["subject_id"]),
        kind=kind,
        level=coerce_level(kind, row["level"]),
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
        visibility=RelationshipVisibility(row["visibility"]),
    )


# --- consequence ----------------------------------------------------------


def consequence_row(consequence: Consequence) -> dict[str, object]:
    return {
        "id": str(consequence.id),
        "world_instance_id": str(consequence.world_instance_id),
        "source_event_id": str(consequence.source_event_id),
        "rule_key": consequence.rule_key,
        "type": consequence.type.value,
        "scale": consequence.scale.value,
        "visibility": consequence.visibility.value,
        "trigger_kind": consequence.trigger.kind.value,
        "trigger_ticks": consequence.trigger.delay_ticks,
        "trigger_event_type": (
            consequence.trigger.event_type.value
            if consequence.trigger.event_type is not None
            else None
        ),
        "effect": consequence.effect.value,
        "payload": dict(consequence.payload),
        "status": consequence.status.value,
        "due_tick": consequence.due_tick,
        "created_at": consequence.created_at,
        "applied_at": consequence.applied_at,
        "applied_event_id": (
            str(consequence.applied_event_id)
            if consequence.applied_event_id is not None
            else None
        ),
    }


def consequence_cause_row(
    consequence: Consequence, cause: ConsequenceCause, position: int
) -> dict[str, object]:
    return {
        "world_instance_id": str(consequence.world_instance_id),
        "consequence_id": str(consequence.id),
        "event_id": str(cause.event_id),
        "origin": cause.origin.value,
        "position": position,
    }


def consequence_from_row(row: dict, causes: list[tuple[str, str]]) -> Consequence:
    trigger = trigger_from_row(row)
    return Consequence(
        id=ConsequenceId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        causes=tuple(
            ConsequenceCause(event_id=EventId(event_id), origin=CauseOrigin(origin))
            for event_id, origin in causes
        ),
        type=ConsequenceType(row["type"]),
        scale=ConsequenceScale(row["scale"]),
        visibility=ConsequenceVisibility(row["visibility"]),
        trigger=trigger,
        effect=ConsequenceEffect(row["effect"]),
        payload=dict(row["payload"] or {}),
        due_tick=int(row["due_tick"]),
        created_at=as_utc(row["created_at"]),
        status=ConsequenceStatus(row["status"]),
        rule_key=row["rule_key"],
        applied_at=as_utc(row["applied_at"]) if row["applied_at"] is not None else None,
        applied_event_id=(
            EventId(row["applied_event_id"]) if row["applied_event_id"] is not None else None
        ),
    )


def trigger_from_row(row: dict) -> ConsequenceTrigger:
    kind = TriggerKind(row["trigger_kind"])
    if kind is TriggerKind.AFTER_TICKS:
        return ConsequenceTrigger.after_ticks(int(row["trigger_ticks"]))
    if kind is TriggerKind.ON_EVENT_TYPE:
        return ConsequenceTrigger.on_event_type(str(row["trigger_event_type"]))
    return ConsequenceTrigger.immediate()
