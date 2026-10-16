"""Associate one case evidence link with a theory stance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._case_utils import commit_case_event, load_open_case
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.investigations.case import CaseTheoryEvidenceLink, CaseTheoryEvidenceStance
from world_error.domain.shared.kernel import (
    CaseEvidenceLinkId,
    CaseId,
    CaseTheoryId,
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class LinkTheoryEvidenceCommand:
    world_instance_id: WorldInstanceId
    case_id: CaseId
    actor_id: CharacterId
    theory_id: CaseTheoryId
    evidence_link_id: CaseEvidenceLinkId
    stance: CaseTheoryEvidenceStance


class LinkTheoryEvidenceHandler:
    ACTION = "LINK_THEORY_EVIDENCE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def handle(self, command: LinkTheoryEvidenceCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance, expected_version, case, actor = load_open_case(
                    uow, command.world_instance_id, command.case_id, command.actor_id
                )
                theory = uow.cases.get_theory(instance.id, command.theory_id)
                evidence = uow.cases.get_evidence_link(instance.id, command.evidence_link_id)
                if theory.case_id != case.id or evidence.case_id != case.id:
                    raise DomainError(ErrorCode.NOT_ALLOWED, "theory and evidence must belong to this case")
                if theory.visibility.value == "PRIVATE" and theory.author_id != actor.id:
                    raise DomainError(ErrorCode.NOT_ALLOWED, "private theory belongs to another character")

                existing = next(
                    (
                        link
                        for link in uow.cases.list_theory_evidence(instance.id, theory.id)
                        if link.evidence_link_id == evidence.id
                    ),
                    None,
                )
                if existing is not None:
                    if existing.stance is command.stance:
                        return ActionResult.success(
                            self.ACTION,
                            payload={"already_linked": True, "theory_id": str(theory.id)},
                        )
                    raise DomainError(
                        ErrorCode.CONFLICT,
                        "evidence already has a different stance for this theory",
                    )

                now = self._clock.now()
                link = CaseTheoryEvidenceLink(
                    world_instance_id=instance.id,
                    theory_id=theory.id,
                    evidence_link_id=evidence.id,
                    stance=command.stance,
                    added_by=actor.id,
                    added_at=now,
                )
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.THEORY_EVIDENCE_LINKED,
                    created_at=now,
                    executed_at=now,
                    actor=str(actor.id),
                    target=str(theory.id),
                    cause="link_theory_evidence",
                    payload={
                        "case_id": str(case.id),
                        "theory_id": str(theory.id),
                        "evidence_link_id": str(evidence.id),
                        "stance": command.stance.value,
                        "added_by": str(actor.id),
                    },
                    result="success",
                )
                uow.cases.add_theory_evidence_link(link)
                commit_case_event(uow, instance, expected_version, event)

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "case_id": str(case.id),
                    "theory_id": str(theory.id),
                    "evidence_link_id": str(evidence.id),
                    "stance": command.stance.value,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)