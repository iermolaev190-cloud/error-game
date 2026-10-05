"""Изменение отношения между субъектами (примитив).

Меняет ровно один вид отношения на одну ступень по его лестнице. Это самый
низкий уровень: значимые действия (``apply_significant_action``) выражаются
через те же шаги.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._subjects import (
    ensure_relationship_subject_alive,
    resolve_subject,
)
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipDirection,
    RelationshipKind,
    RelationshipVisibility,
    SubjectRef,
    baseline_level,
    step_level,
)
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
class ChangeRelationshipCommand:
    world_instance_id: WorldInstanceId
    holder: SubjectRef
    subject: SubjectRef
    kind: RelationshipKind
    direction: RelationshipDirection
    visibility: RelationshipVisibility | None = None
    reason: str = "manual"
    cause: str = "change_relationship"


class ChangeRelationshipHandler:
    ACTION = "CHANGE_RELATIONSHIP"

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

    def handle(self, command: ChangeRelationshipCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version

                resolve_subject(uow, instance.id, command.holder)
                resolve_subject(uow, instance.id, command.subject)
                ensure_relationship_subject_alive(uow, instance.id, command.holder)
                ensure_relationship_subject_alive(uow, instance.id, command.subject)
                if command.holder == command.subject:
                    raise DomainError(
                        ErrorCode.INVALID_ACTION,
                        "a subject cannot have a relationship with itself",
                    )

                existing = uow.relationships.find(
                    instance.id, command.holder, command.subject, command.kind
                )
                current_level = existing.level if existing is not None else baseline_level(command.kind)
                new_level = step_level(command.kind, current_level, command.direction)
                current_visibility = (
                    existing.visibility if existing is not None else RelationshipVisibility.PUBLIC
                )
                new_visibility = command.visibility or current_visibility
                visibility_changed = new_visibility is not current_visibility

                if new_level is None and not visibility_changed:
                    # Край лестницы: менять нечего, состояние не меняется —
                    # значит и события нет.
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "changed": False,
                            "holder_type": command.holder.type.value,
                            "holder_id": command.holder.id,
                            "subject_type": command.subject.type.value,
                            "subject_id": command.subject.id,
                            "kind": command.kind.value,
                            "level": current_level.value,
                            "visibility": current_visibility.value,
                        },
                    )

                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.RELATIONSHIP_CHANGED,
                    created_at=now,
                    executed_at=now,
                    actor=command.holder.id,
                    target=command.subject.id,
                    cause=command.cause,
                    payload={
                        "holder_type": command.holder.type.value,
                        "holder_id": command.holder.id,
                        "subject_type": command.subject.type.value,
                        "subject_id": command.subject.id,
                        "reason": command.reason,
                        "changes": [
                            {
                                "kind": command.kind.value,
                                "from": current_level.value,
                                "to": current_level.value if new_level is None else new_level.value,
                            }
                        ],
                        **({"visibility": new_visibility.value} if visibility_changed else {}),
                    },
                    result="success",
                )
                instance.register_applied_event(event)

                relationship = existing or Relationship.create(
                    id=self._new_relationship_id(),
                    holder=command.holder,
                    holder_instance_id=instance.id,
                    subject=command.subject,
                    subject_instance_id=instance.id,
                    kind=command.kind,
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
                    "holder_type": command.holder.type.value,
                    "holder_id": command.holder.id,
                    "subject_type": command.subject.type.value,
                    "subject_id": command.subject.id,
                    "kind": command.kind.value,
                    "from": current_level.value,
                    "to": current_level.value if new_level is None else new_level.value,
                    "visibility": new_visibility.value,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
