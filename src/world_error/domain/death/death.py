"""Canonical death-event projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
)


@dataclass(frozen=True, slots=True)
class DeathEvent:
    id: EventId
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    cause_event_id: EventId
    occurred_at: datetime

    @classmethod
    def from_event(cls, event: Event) -> "DeathEvent":
        if event.type is not EventType.DEATH_EVENT:
            raise DomainError(ErrorCode.INVALID_ACTION, "event is not DEATH_EVENT")
        character_id = event.payload.get("character_id")
        cause_event_id = event.payload.get("cause_event_id")
        if not character_id or not cause_event_id:
            raise DomainError(ErrorCode.INVALID_ACTION, "death event requires character and cause")
        if event.target != str(character_id):
            raise DomainError(ErrorCode.NOT_ALLOWED, "death event target does not match payload")
        return cls(
            id=event.id,
            world_instance_id=event.world_instance_id,
            character_id=CharacterId(str(character_id)),
            cause_event_id=EventId(str(cause_event_id)),
            occurred_at=event.executed_at or event.created_at,
        )
