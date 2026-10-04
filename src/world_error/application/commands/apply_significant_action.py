"""Значимое действие меняет отношение (05_NPCS §13, §29).

Правило живёт в домене (``domain/relationships/rules.py``), здесь — только
применение: держатель отношения (holder) меняет своё мнение о том, кто действовал
(actor). Одно действие = одно событие, даже если меняются два вида сразу.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._subjects import resolve_subject
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipKind,
    SubjectRef,
    baseline_level,
    step_level,
)
from world_error.domain.relationships.rules import SignificantAction, effects_of
from world_error.domain.shared.kernel import (
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    RelationshipId,
    WorldInstanceId,
    new_event_id,
    new_relationship_id,
)


@dataclass(frozen=True, slots=True)
class ApplySignificantActionCommand:
    world_instance_id: WorldInstanceId
    actor: SubjectRef
    holder: SubjectRef
    action: SignificantAction
    cause: str = "significant_action"


class ApplySignificantActionHandler:
    ACTION = "SIGNIFICANT_ACTION"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_relationship_id_factory: Callable[[], RelationshipId] = new_relationship_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_relationship_id = new_relationship_id_factory

    def handle(self, command: ApplySignificantActionCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version

                resolve_subject(uow, instance.id, command.actor)
                resolve_subject(uow, instance.id, command.holder)
                if command.actor == command.holder:
                    raise DomainError(
                        ErrorCode.INVALID_ACTION,
                        "a significant action must involve two different subjects",
                    )

                plan: list[tuple[Relationship | None, RelationshipKind]] = []
                changes: list[dict[str, str]] = []
                for kind, direction in effects_of(command.action):
                    existing = uow.relationships.find(
                        instance.id, command.holder, command.actor, kind
                    )
                    current_level = (
                        existing.level if existing is not None else baseline_level(kind)
                    )
                    new_level = step_level(kind, current_level, direction)
                    if new_level is None:
                        continue  # край лестницы: этот вид не меняется
                    plan.append((existing, kind))
                    changes.append(
                        {
                            "kind": kind.value,
                            "from": current_level.value,
                            "to": new_level.value,
                        }
                    )

                if not changes:
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "changed": False,
                            "reason": command.action.value,
                            "holder_id": command.holder.id,
                            "subject_id": command.actor.id,
                        },
                    )

                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.RELATIONSHIP_CHANGED,
                    created_at=now,
                    executed_at=now,
                    actor=command.actor.id,
                    target=command.holder.id,
                    cause=command.cause,
                    payload={
                        "holder_type": command.holder.type.value,
                        "holder_id": command.holder.id,
                        "subject_type": command.actor.type.value,
                        "subject_id": command.actor.id,
                        "reason": command.action.value,
                        "changes": changes,
                    },
                    result="success",
                )
                instance.register_applied_event(event)

                for existing, kind in plan:
                    relationship = existing or Relationship.create(
                        id=self._new_relationship_id(),
                        holder=command.holder,
                        holder_instance_id=instance.id,
                        subject=command.actor,
                        subject_instance_id=instance.id,
                        kind=kind,
                        now=now,
                    )
                    relationship.apply(event)
                    if existing is None:
                        uow.relationships.add(relationship)
                    else:
                        uow.relationships.save(relationship)

                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "changed": True,
                    "reason": command.action.value,
                    "holder_id": command.holder.id,
                    "subject_id": command.actor.id,
                    "changes": changes,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
