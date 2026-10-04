"""Реализации портов поверх SQLAlchemy Core.

Правило изоляции: любой запрос к журналу событий ограничен одним
``world_instance_id``, поэтому данные разных WORLD INSTANCE не смешиваются.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import DomainError, ErrorCode, EventId, WorldInstanceId
from world_error.domain.world.instance import (
    InstanceEnvironment,
    InstanceLifecycle,
    WorldInstance,
    WorldState,
)
from world_error.infrastructure.db.tables import events, world_instances


def _as_utc(value: datetime) -> datetime:
    """SQLite не хранит tzinfo: возвращаем время как UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_utc_optional(value: datetime | None) -> datetime | None:
    return None if value is None else _as_utc(value)


def _instance_row(instance: WorldInstance) -> dict[str, object]:
    return {
        "id": str(instance.id),
        "telegram_chat_id": instance.telegram_chat_id,
        "seed": instance.seed,
        "environment": instance.environment.value,
        "lifecycle": instance.lifecycle.value,
        "current_time": instance.state.current_time,
        "world_tick": instance.state.world_tick,
        "state_version": instance.state.state_version,
        "created_at": instance.created_at,
    }


def _instance_from_row(row: dict) -> WorldInstance:
    return WorldInstance(
        id=WorldInstanceId(row["id"]),
        telegram_chat_id=row["telegram_chat_id"],
        seed=row["seed"],
        environment=InstanceEnvironment(row["environment"]),
        lifecycle=InstanceLifecycle(row["lifecycle"]),
        created_at=_as_utc(row["created_at"]),
        state=WorldState(
            current_time=_as_utc(row["current_time"]),
            world_tick=row["world_tick"],
            state_version=row["state_version"],
        ),
    )


def _event_row(event: Event) -> dict[str, object]:
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


def _event_from_row(row: dict) -> Event:
    return Event(
        id=EventId(row["id"]),
        world_instance_id=WorldInstanceId(row["world_instance_id"]),
        type=EventType(row["type"]),
        created_at=_as_utc(row["created_at"]),
        actor=row["actor"],
        target=row["target"],
        cause=row["cause"],
        payload=dict(row["payload"] or {}),
        executed_at=_as_utc_optional(row["executed_at"]),
        result=row["result"],
    )


class SqlWorldInstanceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, instance: WorldInstance) -> None:
        self._session.execute(insert(world_instances).values(**_instance_row(instance)))

    def get(self, world_instance_id: WorldInstanceId) -> WorldInstance:
        row = (
            self._session.execute(
                select(world_instances).where(world_instances.c.id == str(world_instance_id))
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"world instance not found: {world_instance_id}")
        return _instance_from_row(dict(row))

    def save(self, instance: WorldInstance) -> None:
        result = self._session.execute(
            update(world_instances)
            .where(world_instances.c.id == str(instance.id))
            .values(**_instance_row(instance))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"world instance not found: {instance.id}")


class SqlEventLogRepository:
    """Append-only журнал событий с идемпотентностью по ``(instance, event_id)``."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: Event) -> None:
        if self.has_event(event.world_instance_id, event.id):
            raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event.id}")
        try:
            self._session.execute(insert(events).values(**_event_row(event)))
        except IntegrityError as exc:  # защита на уровне БД
            raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event.id}") from exc

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
        return [_event_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]
