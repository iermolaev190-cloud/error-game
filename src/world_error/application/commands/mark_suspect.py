"""Mark or update an existing world subject as a case suspect."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._case_utils import commit_case_event, load_open_case
from world_error.application.commands._subjects import resolve_subject
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.investigations.case import CaseSuspectLink, CaseSuspectStatus
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import SubjectRef
from world_error.domain.shared.kernel import (
    CaseId,
    CaseSuspectLinkId,
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
    new_case_suspect_link_id,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class MarkSuspectCommand:
    world_instance_id: WorldInstanceId
    case_id: CaseId
    actor_id: CharacterId
    subject_type: SubjectType
    subject_id: str
    reason: str
    status: CaseSuspectStatus = CaseSuspectStatus.SUSPECTED


class MarkSuspectHandler:
    ACTION = "MARK_SUSPECT"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_link_id_factory: Callable[[], CaseSuspectLinkId] = new_case_suspect_link_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_link_id = new_link_id_factory

    def handle(self, command: MarkSuspectCommand) -> ActionResult:
        try:
            if not command.reason.strip():
                raise DomainError(ErrorCode.INVALID_ACTION, "suspect reason must not be empty")
            with self._uow_factory() as uow:
                instance, expected_version, case, actor = load_open_case(
                    uow, command.world_instance_id, command.case_id, command.actor_id
                )
                subject = SubjectRef(type=command.subject_type, id=command.subject_id)
                resolve_subject(uow, instance.id, subject)
                existing = uow.cases.find_suspect(
                    instance.id, case.id, command.subject_type, command.subject_id
                )
                if (
                    existing is not None
                    and existing.status is command.status
                    and existing.reason == command.reason
                ):
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "already_marked": True,
                            "case_id": str(case.id),
                            "suspect_link_id": str(existing.id),
                        },
                    )

                now = self._clock.now()
                link = existing or CaseSuspectLink(
                    id=self._new_link_id(),
                    world_instance_id=instance.id,
                    case_id=case.id,
                    subject_type=command.subject_type,
                    subject_id=command.subject_id,
                    reason=command.reason,
                    marked_by=actor.id,
                    status=command.status,
                    marked_at=now,
                )
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.SUSPECT_MARKED,
                    created_at=now,
                    executed_at=now,
                    actor=str(actor.id),
                    target=command.subject_id,
                    cause="mark_suspect",
                    payload={
                        "case_id": str(case.id),
                        "suspect_link_id": str(link.id),
                        "subject_type": command.subject_type.value,
                        "subject_id": command.subject_id,
                        "reason": command.reason,
                        "status": command.status.value,
                        "marked_by": str(actor.id),
                    },
                    result="success",
                )
                if existing is None:
                    uow.cases.add_suspect(link)
                else:
                    link.apply(event)
                    uow.cases.save_suspect(link)
                commit_case_event(uow, instance, expected_version, event)

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "case_id": str(case.id),
                    "suspect_link_id": str(link.id),
                    "subject_type": command.subject_type.value,
                    "subject_id": command.subject_id,
                    "status": link.status.value,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)