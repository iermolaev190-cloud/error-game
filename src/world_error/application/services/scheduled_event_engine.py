"""Deterministic, restart-safe scheduled-event pump; no background worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    Clock,
    EventId,
    ScheduledEventId,
    WorldInstanceId,
    new_event_id,
)
from world_error.domain.time.scheduled_event import (
    ScheduledEvent,
    ScheduledEventStatus,
    ScheduledTriggerKind,
)
from world_error.domain.time.time_point import TimePoint, TimePointKind
from world_error.domain.world.instance import InstanceLifecycle


@dataclass(frozen=True, slots=True)
class ScheduledPumpOutcome:
    applied: tuple[ScheduledEventId, ...] = ()
    event_ids: tuple[EventId, ...] = ()
    limit_reached: bool = False

    @property
    def steps(self) -> int:
        return len(self.applied)

    @property
    def changed(self) -> bool:
        return bool(self.applied)


class ScheduledEventEngine:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def pump(
        self, world_instance_id: WorldInstanceId, *, max_steps: int
    ) -> ScheduledPumpOutcome:
        applied: list[ScheduledEventId] = []
        event_ids: list[EventId] = []
        while len(applied) < max_steps:
            outcome = self._apply_next_due(world_instance_id)
            if outcome is None:
                break
            scheduled_event_id, event_id = outcome
            applied.append(scheduled_event_id)
            event_ids.append(event_id)
        limit_reached = len(applied) >= max_steps and self.has_due(world_instance_id)
        return ScheduledPumpOutcome(
            applied=tuple(applied), event_ids=tuple(event_ids), limit_reached=limit_reached
        )

    def has_due(self, world_instance_id: WorldInstanceId) -> bool:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            if instance.lifecycle is not InstanceLifecycle.ACTIVE:
                return False
            now = self._clock.now()
            world_time = instance.world_time_at(now)
            return any(
                self._is_due(uow, instance.world_tick, world_time, item)
                for item in uow.scheduled_events.list_pending(instance.id)
            )

    def _is_due(self, uow, current_tick: int, world_time, item: ScheduledEvent) -> bool:  # noqa: ANN001
        matching_event_seen = False
        if item.trigger.kind is ScheduledTriggerKind.ON_EVENT_TYPE:
            matching_event_seen = uow.events.has_event_of_type_since(
                item.world_instance_id,
                item.trigger.event_type,
                item.created_event_id,
            )
        return item.trigger.is_due(
            current_tick=current_tick,
            current_time=world_time,
            matching_event_seen=matching_event_seen,
        )

    def _apply_next_due(
        self, world_instance_id: WorldInstanceId
    ) -> tuple[ScheduledEventId, EventId] | None:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            if instance.lifecycle is not InstanceLifecycle.ACTIVE:
                return None
            now = self._clock.now()
            world_time = instance.world_time_at(now)
            due = next(
                (
                    item
                    for item in uow.scheduled_events.list_pending(instance.id)
                    if self._is_due(uow, instance.state.world_tick, world_time, item)
                ),
                None,
            )
            scheduled_event_id = None if due is None else due.id
        if scheduled_event_id is None:
            return None
        return self._apply_one(world_instance_id, scheduled_event_id)

    def _apply_one(
        self, world_instance_id: WorldInstanceId, scheduled_event_id: ScheduledEventId
    ) -> tuple[ScheduledEventId, EventId] | None:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            if instance.lifecycle is not InstanceLifecycle.ACTIVE:
                return None
            scheduled = uow.scheduled_events.get(instance.id, scheduled_event_id)
            now = self._clock.now()
            if not self._is_due(uow, instance.state.world_tick, instance.world_time_at(now), scheduled):
                return None
            expected_version = instance.state.state_version
            event_id = self._new_event_id()
            event = Event(
                id=event_id,
                world_instance_id=instance.id,
                type=EventType.SCHEDULED_EVENT_TRIGGERED,
                created_at=now,
                executed_at=now,
                actor="system",
                target=scheduled.event_key,
                cause=f"scheduled:{scheduled.id}",
                payload={
                    "scheduled_event_id": str(scheduled.id),
                    "cause_event_id": str(scheduled.cause_event_id),
                    "event_key": scheduled.event_key,
                    "event_payload": dict(scheduled.payload),
                },
                result="success",
            ).with_time_point(
                TimePoint(
                    event_id=event_id,
                    kind=TimePointKind.OCCURRED_AT,
                    at=instance.world_time_at(now),
                )
            )
            scheduled.mark_applied(event_id=event_id, now=now)
            instance.register_applied_event(event)
            uow.world_instances.save(instance, expected_state_version=expected_version)
            uow.events.append(event)
            uow.scheduled_events.save(scheduled)
            uow.commit()
            return scheduled.id, event.id
