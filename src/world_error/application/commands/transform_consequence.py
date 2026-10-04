"""Transform a pending consequence into a new consequence via two events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.consequences.consequence import Consequence, ConsequenceCause, origin_of
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceStatus,
    ConsequenceType,
    ConsequenceVisibility,
)
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    Clock,
    ConsequenceId,
    DomainError,
    EventId,
    WorldInstanceId,
    new_consequence_id,
    new_event_id,
)
from world_error.domain.consequences.consequence import ConsequenceTrigger


@dataclass(frozen=True, slots=True)
class TransformConsequenceCommand:
    world_instance_id: WorldInstanceId
    consequence_id: ConsequenceId
    type: ConsequenceType
    scale: ConsequenceScale
    visibility: ConsequenceVisibility
    trigger: ConsequenceTrigger
    effect: ConsequenceEffect
    payload: Mapping[str, Any]
    actor: str = "system"


class TransformConsequenceHandler:
    ACTION = "TRANSFORM_CONSEQUENCE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_consequence_id_factory: Callable[[], ConsequenceId] = new_consequence_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_consequence_id = new_consequence_id_factory

    def handle(self, command: TransformConsequenceCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                previous = uow.consequences.get(instance.id, command.consequence_id)
                if previous.status is ConsequenceStatus.TRANSFORMED:
                    return ActionResult.success(
                        self.ACTION,
                        payload={"consequence_id": str(previous.id), "already_transformed": True},
                    )

                expected_version = instance.state.state_version
                now = self._clock.now()
                transform_event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.CONSEQUENCE_TRANSFORMED,
                    created_at=now,
                    executed_at=now,
                    actor=command.actor,
                    target=str(previous.id),
                    cause=f"consequence:{previous.id}",
                    payload={"consequence_id": str(previous.id)},
                    result="success",
                )
                if not previous.mark_transformed(now=now):
                    return ActionResult.success(
                        self.ACTION,
                        payload={"consequence_id": str(previous.id), "already_transformed": True},
                    )

                instance.register_applied_event(transform_event)
                replacement = Consequence.create(
                    id=self._new_consequence_id(),
                    world_instance_id=instance.id,
                    causes=(ConsequenceCause(transform_event.id, origin_of(transform_event)),),
                    type=command.type,
                    scale=command.scale,
                    visibility=command.visibility,
                    trigger=command.trigger,
                    effect=command.effect,
                    payload=command.payload,
                    created_tick=instance.state.world_tick,
                    now=now,
                )
                created_event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.CONSEQUENCE_CREATED,
                    created_at=now,
                    executed_at=now,
                    actor=command.actor,
                    target=str(replacement.id),
                    cause=f"consequence_transform:{previous.id}",
                    payload={
                        "consequence_id": str(replacement.id),
                        "source_event_id": str(transform_event.id),
                        "type": replacement.type.value,
                        "effect": replacement.effect.value,
                        "trigger": replacement.trigger.as_payload(),
                    },
                    result="success",
                )
                instance.register_applied_event(created_event)

                uow.events.append(transform_event)
                uow.consequences.save(previous)
                uow.consequences.add(replacement)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(created_event)
                uow.commit()
            return ActionResult.success(
                self.ACTION,
                event_ids=(transform_event.id, created_event.id),
                payload={
                    "consequence_id": str(previous.id),
                    "transformed_to": str(replacement.id),
                    "already_transformed": False,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)