"""Schedule one deterministic instance-scoped event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    ScheduledEventId,
    WorldInstanceId,
    new_event_id,
    new_scheduled_event_id,
)
from world_error.domain.time.scheduled_event import (
    ScheduledEvent,
    ScheduledEventStatus,
    ScheduledEventTrigger,
    ScheduledTriggerKind,
)


@dataclass(frozen=True, slots=True)
class ScheduleEventCommand:
    world_instance_id: WorldInstanceId
    cause_event_id: EventId
    event_key: str
    idempotency_key: str
    trigger_kind: ScheduledTriggerKind
    payload: Mapping[str, Any]
    due_tick: int | None = None
    due_time: datetime | None = None
    trigger_event_type: EventType | None = None
    actor: str = "system"


class ScheduleEventHandler:
    ACTION = "SCHEDULE_EVENT"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_scheduled_event_id_factory: Callable[[], ScheduledEventId] = new_scheduled_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_scheduled_event_id = new_scheduled_event_id_factory

    def handle(self, command: ScheduleEventCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                existing = uow.scheduled_events.find_by_idempotency_key(
                    instance.id, command.idempotency_key
                )
                if existing is not None:
                    if (
                        existing.cause_event_id != command.cause_event_id
                        or existing.event_key != command.event_key
                    ):
                        raise DomainError(
                            ErrorCode.ALREADY_PROCESSED,
                            f"idempotency key reused for another scheduled event: {command.idempotency_key}",
                        )
                    return ActionResult.success(
                        self.ACTION,
                        event_ids=(existing.created_event_id,),
                        payload={
                            "scheduled_event_id": str(existing.id),
                            "status": existing.status.value,
                            "already_scheduled": True,
                        },
                    )

                uow.events.get(instance.id, command.cause_event_id)
                now = self._clock.now()
                trigger = _make_trigger(command, instance.state.world_tick)
                scheduled_event_id = self._new_scheduled_event_id()
                created_event_id = self._new_event_id()
                scheduled = ScheduledEvent(
                    id=scheduled_event_id,
                    world_instance_id=instance.id,
                    cause_event_id=command.cause_event_id,
                    created_event_id=created_event_id,
                    idempotency_key=command.idempotency_key,
                    trigger=trigger,
                    event_key=command.event_key,
                    payload=dict(command.payload),
                    created_at=now,
                )
                event = Event(
                    id=created_event_id,
                    world_instance_id=instance.id,
                    type=EventType.SCHEDULED_EVENT_CREATED,
                    created_at=now,
                    executed_at=now,
                    actor=command.actor,
                    target=str(scheduled_event_id),
                    cause=f"event:{command.cause_event_id}",
                    payload={
                        "scheduled_event_id": str(scheduled_event_id),
                        "cause_event_id": str(command.cause_event_id),
                        "event_key": command.event_key,
                        "trigger_kind": trigger.kind.value,
                        "due_tick": trigger.due_tick,
                        "due_time": None if trigger.due_time is None else trigger.due_time.isoformat(),
                        "trigger_event_type": (
                            None if trigger.event_type is None else trigger.event_type.value
                        ),
                    },
                    result="success",
                )
                instance.register_applied_event(event)
                expected_version = instance.state.state_version - 1
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.scheduled_events.add(scheduled)
                uow.commit()
            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "scheduled_event_id": str(scheduled_event_id),
                    "status": ScheduledEventStatus.PENDING.value,
                    "due_tick": trigger.due_tick,
                    "due_time": None if trigger.due_time is None else trigger.due_time.isoformat(),
                    "already_scheduled": False,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)


def _make_trigger(
    command: ScheduleEventCommand, current_tick: int
) -> ScheduledEventTrigger:
    kind = command.trigger_kind
    if kind is ScheduledTriggerKind.IMMEDIATE:
        if command.due_tick is not None or command.due_time is not None:
            raise DomainError(ErrorCode.INVALID_ACTION, "IMMEDIATE does not accept a due value")
        return ScheduledEventTrigger(kind=kind, due_tick=current_tick)
    if kind is ScheduledTriggerKind.AT_TICK:
        if command.due_tick is None or command.due_time is not None:
            raise DomainError(ErrorCode.INVALID_ACTION, "AT_TICK requires only due_tick")
        return ScheduledEventTrigger(kind=kind, due_tick=command.due_tick)
    if kind is ScheduledTriggerKind.AT_TIME:
        if command.due_time is None or command.due_tick is not None:
            raise DomainError(ErrorCode.INVALID_ACTION, "AT_TIME requires only due_time")
        return ScheduledEventTrigger(kind=kind, due_time=command.due_time)
    if command.due_tick is not None or command.due_time is not None:
        raise DomainError(ErrorCode.INVALID_ACTION, "ON_EVENT_TYPE uses creation tick as its due_tick")
    return ScheduledEventTrigger(
        kind=kind,
        due_tick=current_tick,
        event_type=command.trigger_event_type,
    )
