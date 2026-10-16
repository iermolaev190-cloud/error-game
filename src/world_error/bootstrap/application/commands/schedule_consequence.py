"""Явное планирование последствия (AUTHORIAL-уровень, 13_CONSEQUENCES §77).

Это самый низкий уровень системы последствий: «вот событие-причина, вот что
должно из-за него измениться». Правила из контента (``content/consequences``)
пользуются этим же путём, поэтому создание последствия всегда идёт через
``CONSEQUENCE_CREATED`` и никогда — в обход событий.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.consequences.consequence import (
    Consequence,
    ConsequenceCause,
    ConsequenceTrigger,
    origin_of,
)
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    ConsequenceScale,
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


@dataclass(frozen=True, slots=True)
class ScheduleConsequenceCommand:
    world_instance_id: WorldInstanceId
    cause_event_ids: tuple[EventId, ...]
    type: ConsequenceType
    scale: ConsequenceScale
    visibility: ConsequenceVisibility
    trigger: ConsequenceTrigger
    effect: ConsequenceEffect
    payload: Mapping[str, Any] = field(default_factory=dict)
    rule_key: str | None = None
    cause: str = "schedule_consequence"


class ScheduleConsequenceHandler:
    ACTION = "SCHEDULE_CONSEQUENCE"

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

    def handle(self, command: ScheduleConsequenceCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version

                causes: list[ConsequenceCause] = []
                for event_id in command.cause_event_ids:
                    # Событие ищется в своём INSTANCE: причина из чужого мира не
                    # находится и даёт NOT_FOUND.
                    cause_event = uow.events.get(instance.id, event_id)
                    causes.append(
                        ConsequenceCause(event_id=cause_event.id, origin=origin_of(cause_event))
                    )

                now = self._clock.now()
                consequence = Consequence.create(
                    id=self._new_consequence_id(),
                    world_instance_id=instance.id,
                    causes=causes,
                    type=command.type,
                    scale=command.scale,
                    visibility=command.visibility,
                    trigger=command.trigger,
                    effect=command.effect,
                    payload=command.payload,
                    created_tick=instance.state.world_tick,
                    now=now,
                    rule_key=command.rule_key,
                )

                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.CONSEQUENCE_CREATED,
                    created_at=now,
                    executed_at=now,
                    actor=None,
                    target=str(consequence.id),
                    cause=command.cause,
                    payload={
                        "consequence_id": str(consequence.id),
                        "type": consequence.type.value,
                        "scale": consequence.scale.value,
                        "visibility": consequence.visibility.value,
                        "trigger": consequence.trigger.as_payload(),
                        "effect": consequence.effect.value,
                        "effect_payload": dict(consequence.payload),
                        "cause_event_ids": [
                            str(cause.event_id) for cause in consequence.causes
                        ],
                        "origins": [cause.origin.value for cause in consequence.causes],
                        "due_tick": consequence.due_tick,
                        "rule_key": consequence.rule_key,
                    },
                    result="success",
                )
                instance.register_applied_event(event)

                uow.consequences.add(consequence)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "consequence_id": str(consequence.id),
                    "status": consequence.status.value,
                    "type": consequence.type.value,
                    "scale": consequence.scale.value,
                    "visibility": consequence.visibility.value,
                    "trigger": consequence.trigger.kind.value,
                    "effect": consequence.effect.value,
                    "due_tick": consequence.due_tick,
                    "rule_key": consequence.rule_key,
                    "cause_event_ids": tuple(str(cause.event_id) for cause in consequence.causes),
                    "origins": tuple(cause.origin.value for cause in consequence.causes),
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
