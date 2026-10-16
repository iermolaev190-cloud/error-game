"""Attach an existing character Knowledge record to a public case."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._case_utils import commit_case_event, load_open_case
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.investigations.case import CaseEvidenceLink, CaseEvidenceRelevance
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    CaseEvidenceLinkId,
    CaseId,
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    InformationId,
    WorldInstanceId,
    new_case_evidence_link_id,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class LinkEvidenceCommand:
    world_instance_id: WorldInstanceId
    case_id: CaseId
    actor_id: CharacterId
    information_id: InformationId
    relevance: CaseEvidenceRelevance | None = None


class LinkEvidenceHandler:
    ACTION = "LINK_EVIDENCE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_link_id_factory: Callable[[], CaseEvidenceLinkId] = new_case_evidence_link_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_link_id = new_link_id_factory

    def handle(self, command: LinkEvidenceCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance, expected_version, case, actor = load_open_case(
                    uow, command.world_instance_id, command.case_id, command.actor_id
                )
                information = uow.information.get(instance.id, command.information_id)
                knowledge = uow.knowledge.find(
                    instance.id, SubjectType.CHARACTER, str(actor.id), information.id
                )
                if knowledge is None:
                    raise DomainError(
                        ErrorCode.INVALID_ACTION,
                        "character must inspect Information before linking it as evidence",
                    )

                existing = uow.cases.find_evidence_link(instance.id, case.id, information.id)
                if (
                    existing is not None
                    and existing.knowledge_id == knowledge.id
                    and existing.added_by == actor.id
                    and (command.relevance is None or command.relevance is existing.relevance)
                ):
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "already_linked": True,
                            "case_id": str(case.id),
                            "evidence_link_id": str(existing.id),
                            "information_id": str(information.id),
                        },
                    )

                now = self._clock.now()
                link = existing or CaseEvidenceLink(
                    id=self._new_link_id(),
                    world_instance_id=instance.id,
                    case_id=case.id,
                    information_id=information.id,
                    knowledge_id=None,
                    relevance=CaseEvidenceRelevance.UNKNOWN,
                    added_by=None,
                    added_at=now,
                )
                target_relevance = command.relevance or link.relevance
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.EVIDENCE_LINKED,
                    created_at=now,
                    executed_at=now,
                    actor=str(actor.id),
                    target=str(information.id),
                    cause="link_evidence",
                    payload={
                        "case_id": str(case.id),
                        "evidence_link_id": str(link.id),
                        "information_id": str(information.id),
                        "knowledge_id": str(knowledge.id),
                        "previous_knowledge_id": (
                            None if link.knowledge_id is None else str(link.knowledge_id)
                        ),
                        "added_by": str(actor.id),
                        "relevance": target_relevance.value,
                    },
                    result="success",
                )
                if existing is None:
                    link.knowledge_id = knowledge.id
                    link.added_by = actor.id
                    link.relevance = target_relevance
                    uow.cases.add_evidence_link(link)
                else:
                    link.apply(event)
                    uow.cases.save_evidence_link(link)
                commit_case_event(uow, instance, expected_version, event)

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "case_id": str(case.id),
                    "evidence_link_id": str(link.id),
                    "information_id": str(information.id),
                    "knowledge_id": str(knowledge.id),
                    "updated_knowledge": existing is not None,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)