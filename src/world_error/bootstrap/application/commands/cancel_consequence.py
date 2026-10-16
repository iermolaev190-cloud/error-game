"""Cancel a pending consequence through an append-only domain event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.consequences.vocabulary import ConsequenceStatus
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    Clock,
    ConsequenceId,
    DomainError,
    EventId,
    WorldInstanceId,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class CancelConsequenceCommand:
    world_instance_id: WorldInstanceId
    consequence_id: ConsequenceId
    actor: str = "system"


class CancelConsequenceHandler:
    ACTION = "CANCEL_CONSEQUENCE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def handle(self, command: CancelConsequenceCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                consequence = uow.consequences.get(instance.id, command.consequence_id)
                if consequence.status is ConsequenceStatus.CANCELLED:
                    return ActionResult.success(
                        self.ACTION,
                        payload={"consequence_id": str(consequence.id), "already_cancelled": True},
                    )
                expected_version = instance.state.state_version
                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.CONSEQUENCE_CANCELLED,
                    created_at=now,
                    executed_at=now,
                    actor=command.actor,
                    target=str(consequence.id),
                    cause=f"consequence:{consequence.id}",
                    payload={"consequence_id": str(consequence.id)},
                    result="success",
                )
                consequence.cancel(now=now)
                instance.register_applied_event(event)
                uow.consequences.save(consequence)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()
            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={"consequence_id": str(consequence.id), "already_cancelled": False},
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)