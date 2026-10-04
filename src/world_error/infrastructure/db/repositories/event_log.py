"""Append-only журнал событий."""

from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from world_error.domain.events.event import Event
from world_error.domain.shared.kernel import DomainError, ErrorCode, EventId, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import event_from_row, event_row
from world_error.infrastructure.db.tables import events


class SqlEventLogRepository:
    """Append-only журнал с идемпотентностью по ``(instance, event_id)``.

    Идемпотентность работает для любых типов событий: и для инстанс-событий
    коммита 1, и для событий-действий коммита 2.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: Event) -> None:
        if self.has_event(event.world_instance_id, event.id):
            raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event.id}")
        try:
            self._session.execute(insert(events).values(**event_row(event)))
        except IntegrityError as exc:  # защита на уровне БД
            raise DomainError(
                ErrorCode.ALREADY_PROCESSED, f"event already processed: {event.id}"
            ) from exc

    def has_event(self, world_instance_id: WorldInstanceId, event_id: EventId) -> bool:
        stmt = select(events.c.seq).where(
            events.c.world_instance_id == str(world_instance_id),
            events.c.id == str(event_id),
        )
        return self._session.execute(stmt).first() is not None

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> list[Event]:
        stmt = (
            select(events)
            .where(events.c.world_instance_id == str(world_instance_id))
            .order_by(events.c.seq)
        )
        return [event_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]
