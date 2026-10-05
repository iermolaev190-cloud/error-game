"""Manually mark a contradiction between two case evidence links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._case_utils import commit_case_event, load_open_case
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.investigations.case import CaseContradictionLink
from world_error.domain.shared.kernel import (
    CaseContradictionLinkId,
    CaseEvidenceLinkId,
    CaseId,
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
    new_case_contradiction_link_id,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class MarkContradictionCommand:
    world_instance_id: WorldInstanceId
    case_id: CaseId
    actor_id: CharacterId
    evidence_a_id: CaseEvidenceLinkId
    evidence_b_id: CaseEvidenceLinkId
    note: str


class MarkContradictionHandler:
    ACTION = "MARK_CONTRADICTION"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_link_id_factory: Callable[[], CaseContradictionLinkId] = new_case_contradiction_link_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_link_id = new_link_id_factory

    def handle(self, command: MarkContradictionCommand) -> ActionResult:
        try:
            if command.evidence_a_id == command.evidence_b_id:
                raise DomainError(ErrorCode.INVALID_ACTION, "contradiction requires two different evidence links")
            if not command.note.strip():
                raise DomainError(ErrorCode.INVALID_ACTION, "contradiction note must not be empty")

            with self._uow_factory() as uow:
                instance, expected_version, case, actor = load_open_case(
                    uow, command.world_instance_id, command.case_id, command.actor_id
                )
                evidence_a = uow.cases.get_evidence_link(instance.id, command.evidence_a_id)
                evidence_b = uow.cases.get_evidence_link(instance.id, command.evidence_b_id)
                if evidence_a.case_id != case.id or evidence_b.case_id != case.id:
                    raise DomainError(ErrorCode.NOT_ALLOWED, "contradiction evidence must belong to this case")

                now = self._clock.now()
                link = CaseContradictionLink(
                    id=self._new_link_id(),
                    world_instance_id=instance.id,
                    case_id=case.id,
                    evidence_a_id=evidence_a.id,
                    evidence_b_id=evidence_b.id,
                    note=command.note,
                    marked_by=actor.id,
                    marked_at=now,
                )
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.CONTRADICTION_MARKED,
                    created_at=now,
                    executed_at=now,
                    actor=str(actor.id),
                    target=str(link.id),
                    cause="mark_contradiction",
                    payload={
                        "case_id": str(case.id),
                        "contradiction_link_id": str(link.id),
                        "evidence_a_id": str(evidence_a.id),
                        "evidence_b_id": str(evidence_b.id),
                        "note": link.note,
                        "marked_by": str(actor.id),
                    },
                    result="success",
                )
                uow.cases.add_contradiction(link)
                commit_case_event(uow, instance, expected_version, event)

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={"case_id": str(case.id), "contradiction_link_id": str(link.id)},
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)