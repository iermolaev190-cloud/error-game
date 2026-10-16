"""Instance-scoped persistence for scheduled events."""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.shared.kernel import DomainError, ErrorCode, ScheduledEventId, WorldInstanceId
from world_error.domain.time.scheduled_event import ScheduledEvent
from world_error.infrastructure.db.repositories._mapping import (
    scheduled_event_from_row,
    scheduled_event_row,
)
from world_error.infrastructure.db.tables import scheduled_events


class SqlScheduledEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: ScheduledEvent) -> None:
        self._session.execute(insert(scheduled_events).values(**scheduled_event_row(item)))

    def get(
        self, world_instance_id: WorldInstanceId, scheduled_event_id: ScheduledEventId
    ) -> ScheduledEvent:
        row = (
            self._session.execute(
                select(scheduled_events).where(
                    scheduled_events.c.world_instance_id == str(world_instance_id),
                    scheduled_events.c.id == str(scheduled_event_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"scheduled event not found: {scheduled_event_id}")
        return scheduled_event_from_row(dict(row))

    def find_by_idempotency_key(
        self, world_instance_id: WorldInstanceId, idempotency_key: str
    ) -> ScheduledEvent | None:
        row = (
            self._session.execute(
                select(scheduled_events).where(
                    scheduled_events.c.world_instance_id == str(world_instance_id),
                    scheduled_events.c.idempotency_key == idempotency_key,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else scheduled_event_from_row(dict(row))

    def list_pending(self, world_instance_id: WorldInstanceId) -> list[ScheduledEvent]:
        rows = self._session.execute(
            select(scheduled_events)
            .where(
                scheduled_events.c.world_instance_id == str(world_instance_id),
                scheduled_events.c.status == "PENDING",
            )
            .order_by(scheduled_events.c.seq)
        ).mappings()
        return [scheduled_event_from_row(dict(row)) for row in rows]

    def save(self, item: ScheduledEvent) -> None:
        result = self._session.execute(
            update(scheduled_events)
            .where(
                scheduled_events.c.world_instance_id == str(item.world_instance_id),
                scheduled_events.c.id == str(item.id),
            )
            .values(**scheduled_event_row(item))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"scheduled event not found: {item.id}")