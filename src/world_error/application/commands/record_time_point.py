"""Append a temporal statement about an existing event."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    Clock,
    DomainError,
    EventId,
    WorldInstanceId,
    new_event_id,
)
from world_error.domain.time.time_point import TimePoint


@dataclass(frozen=True, slots=True)
class RecordTimePointCommand:
    world_instance_id: WorldInstanceId
    time_point: TimePoint
    actor: str = "system"


class RecordTimePointHandler:
    ACTION = "RECORD_TIME_POINT"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def handle(self, command: RecordTimePointCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                prior_events = uow.events.list_for_instance(instance.id)
                if any(
                    point == command.time_point
                    for prior_event in prior_events
                    for point in prior_event.time_points
                ):
                    return ActionResult.success(
                        self.ACTION,
                        payload={"already_recorded": True},
                    )
                uow.events.get(instance.id, command.time_point.event_id)
                expected_version = instance.state.state_version
                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.TIME_POINT_RECORDED,
                    created_at=now,
                    executed_at=now,
                    actor=command.actor,
                    target=str(command.time_point.event_id),
                    cause="record_time_point",
                    payload={"time_point": command.time_point.to_metadata()},
                    result="success",
                    metadata={"time_points": [command.time_point.to_metadata()]},
                )
                instance.register_applied_event(event)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()
            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={"already_recorded": False},
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
