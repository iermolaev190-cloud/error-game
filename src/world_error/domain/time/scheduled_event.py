"""Персистентное событие, ожидающее временного или событийного триггера."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    EventId,
    ScheduledEventId,
    WorldInstanceId,
)


class ScheduledTriggerKind(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    AT_TICK = "AT_TICK"
    AT_TIME = "AT_TIME"
    ON_EVENT_TYPE = "ON_EVENT_TYPE"


class ScheduledEventStatus(StrEnum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ScheduledEventTrigger:
    kind: ScheduledTriggerKind
    due_tick: int | None = None
    due_time: datetime | None = None
    event_type: EventType | None = None

    def __post_init__(self) -> None:
        if (self.due_tick is None) == (self.due_time is None):
            raise DomainError(
                ErrorCode.INVALID_ACTION, "exactly one of due_tick and due_time is required"
            )
        if self.kind is ScheduledTriggerKind.AT_TIME:
            if self.due_time is None or self.due_time.tzinfo is None or self.due_tick is not None:
                raise DomainError(ErrorCode.INVALID_ACTION, "AT_TIME requires an aware due_time")
        elif self.due_tick is None or self.due_time is not None:
            raise DomainError(ErrorCode.INVALID_ACTION, f"{self.kind.value} requires due_tick")
        if self.kind is ScheduledTriggerKind.ON_EVENT_TYPE and self.event_type is None:
            raise DomainError(ErrorCode.INVALID_ACTION, "ON_EVENT_TYPE requires event_type")
        if self.kind is not ScheduledTriggerKind.ON_EVENT_TYPE and self.event_type is not None:
            raise DomainError(ErrorCode.INVALID_ACTION, "event_type is only valid for ON_EVENT_TYPE")

    def is_due(
        self,
        *,
        current_tick: int,
        current_time: datetime,
        matching_event_seen: bool = False,
    ) -> bool:
        if self.kind is ScheduledTriggerKind.AT_TIME:
            return current_time >= self.due_time
        if self.kind is ScheduledTriggerKind.ON_EVENT_TYPE:
            return matching_event_seen
        return current_tick >= self.due_tick


@dataclass(slots=True)
class ScheduledEvent:
    id: ScheduledEventId
    world_instance_id: WorldInstanceId
    cause_event_id: EventId
    created_event_id: EventId
    idempotency_key: str
    trigger: ScheduledEventTrigger
    event_key: str
    payload: Mapping[str, Any]
    created_at: datetime
    status: ScheduledEventStatus = ScheduledEventStatus.PENDING
    triggered_event_id: EventId | None = None
    applied_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_key.strip() or not self.idempotency_key.strip():
            raise DomainError(
                ErrorCode.INVALID_ACTION, "scheduled event key and idempotency key are required"
            )
        if self.created_at.tzinfo is None:
            raise DomainError(ErrorCode.INVALID_ACTION, "scheduled event time must be timezone-aware")
        self.payload = dict(self.payload)

    def mark_applied(self, *, event_id: EventId, now: datetime) -> bool:
        if self.status is not ScheduledEventStatus.PENDING:
            return False
        self.status = ScheduledEventStatus.APPLIED
        self.triggered_event_id = event_id
        self.applied_at = now
        return True

    def mark_failed(self, *, event_id: EventId, now: datetime) -> bool:
        if self.status is not ScheduledEventStatus.PENDING:
            return False
        self.status = ScheduledEventStatus.FAILED
        self.triggered_event_id = event_id
        self.applied_at = now
        return True