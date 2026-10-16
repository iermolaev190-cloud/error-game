"""Faction content definitions and instance-scoped state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    FactionId,
    LocationKey,
    WorldInstanceId,
)


class FactionStatus(StrEnum):
    STABLE = "STABLE"
    GROWING = "GROWING"
    DECLINING = "DECLINING"
    CONFLICT = "CONFLICT"
    DIVIDED = "DIVIDED"
    UNDER_ATTACK = "UNDER_ATTACK"
    OCCUPIED = "OCCUPIED"
    UNDERGROUND = "UNDERGROUND"


_STATUS_TRANSITIONS: dict[FactionStatus, frozenset[FactionStatus]] = {
    status: frozenset(candidate for candidate in FactionStatus if candidate is not status)
    for status in FactionStatus
}


@dataclass(frozen=True, slots=True)
class FactionDefinition:
    """Global immutable content; hidden goals never belong to faction state."""

    key: str
    name: str
    description: str
    faction_type: str
    public_goal: str
    locations: tuple[LocationKey, ...]
    hidden_goal: str | None = None


@dataclass(slots=True)
class Faction:
    """A faction's mutable state within exactly one WORLD INSTANCE."""

    id: FactionId
    world_instance_id: WorldInstanceId
    key: str
    status: FactionStatus
    location_keys: tuple[LocationKey, ...]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: FactionId,
        world_instance_id: WorldInstanceId,
        key: str,
        location_keys: tuple[LocationKey, ...],
        now: datetime,
    ) -> "Faction":
        return cls(
            id=id,
            world_instance_id=world_instance_id,
            key=key,
            status=FactionStatus.STABLE,
            location_keys=location_keys,
            created_at=now,
            updated_at=now,
        )

    def apply(self, event: Event) -> None:
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another world instance",
            )
        if event.actor != str(self.id):
            raise DomainError(ErrorCode.NOT_ALLOWED, "event belongs to another faction")
        if event.type is not EventType.FACTION_STATUS_CHANGED:
            raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported event type: {event.type}")
        try:
            from_status = FactionStatus(event.payload["from"])
            to_status = FactionStatus(event.payload["to"])
        except (KeyError, ValueError) as exc:
            raise DomainError(ErrorCode.INVALID_ACTION, "invalid faction status transition") from exc
        if from_status is not self.status or to_status not in _STATUS_TRANSITIONS[self.status]:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"illegal faction status transition: {self.status} -> {to_status}",
            )
        self.status = to_status
        self.updated_at = event.executed_at or event.created_at