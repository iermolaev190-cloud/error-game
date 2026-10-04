"""Сопоставление доменных объектов и строк БД."""

from __future__ import annotations

from datetime import datetime, timezone

from world_error.domain.characters.character import (
    Character,
    CharacterActivity,
    CharacterLifecycle,
)
from world_error.domain.events.event import Event, EventType
from world_error.domain.information.information import Information
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.locations.location import LocationState
from world_error.domain.npcs.npc import Npc, NpcStatus
from world_error.domain.shared.kernel import (
    CharacterId,
    DiscoveryState,
    EventId,
    InformationId,
    KnowledgeId,
    LocationKey,
    NpcId,
    WorldInstanceId,
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
