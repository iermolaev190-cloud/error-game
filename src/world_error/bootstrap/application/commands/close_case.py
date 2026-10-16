"""Close a case only after its authored resolution criteria pass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._case_utils import commit_case_event, load_open_case
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.investigations.case import CaseId, CaseTheoryConfidence, CaseTheoryStatus
from world_error.domain.shared.kernel import (
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
    new_event_id,
)

_ACTION_EVENT_TYPES = {
    "link_evidence": EventType.EVIDENCE_LINKED,
    "create_theory": EventType.THEORY_CREATED,
    "link_theory_evidence": EventType.THEORY_EVIDENCE_LINKED,
    "mark_contradiction": EventType.CONTRADICTION_MARKED,
    "mark_suspect": EventType.SUSPECT_MARKED,
    "add_case_note": EventType.CASE_NOTE_ADDED,
    "add_case_question": EventType.CASE_QUESTION_ADDED,
}
_THEORY_CONFIDENCE_ORDER = {
    CaseTheoryConfidence.SPECULATIVE: 0,
    CaseTheoryConfidence.PLAUSIBLE: 1,
    CaseTheoryConfidence.SUPPORTED: 2,
    CaseTheoryConfidence.CONFIRMED: 3,
}


@dataclass(frozen=True, slots=True)
class CloseCaseCommand:
    world_instance_id: WorldInstanceId
    case_id: CaseId
    actor_id: CharacterId


class CloseCaseHandler:
    ACTION = "CLOSE_CASE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        catalog: ContentCatalog,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def handle(self, command: CloseCaseCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance, expected_version, case, actor = load_open_case(
                    uow, command.world_instance_id, command.case_id, command.actor_id
                )
                definition = self._catalog.case_definition(case.key)
                criteria = definition.resolution_criteria
                evidence = uow.cases.list_evidence(instance.id, case.id)
                theories = uow.cases.list_theories(instance.id, case.id)
                active_theories = [
                    theory for theory in theories if theory.status is not CaseTheoryStatus.REJECTED
                ]
                notes = uow.cases.list_notes(instance.id, case.id)
                questions = uow.cases.list_questions(instance.id, case.id)
                suspects = uow.cases.list_suspects(instance.id, case.id)
                contradictions = uow.cases.list_contradictions(instance.id, case.id)
                theory_evidence = [
                    link
                    for theory in theories
                    for link in uow.cases.list_theory_evidence(instance.id, theory.id)
                ]
                case_events = [
                    event
                    for event in uow.events.list_for_instance(instance.id)
                    if str(event.payload.get("case_id")) == str(case.id)
                ]

                contributors = {
                    str(contributor)
                    for contributor in (
                        [link.added_by for link in evidence]
                        + [theory.author_id for theory in theories]
                        + [note.author_id for note in notes]
                        + [question.added_by for question in questions]
                        + [suspect.marked_by for suspect in suspects]
                        + [link.added_by for link in theory_evidence]
                        + [link.marked_by for link in contradictions]
                    )
                    if contributor is not None
                }
                performed_actions = {
                    action
                    for action, event_type in _ACTION_EVENT_TYPES.items()
                    if any(event.type is event_type for event in case_events)
                }
                missing: list[str] = []
                if len(evidence) < criteria.required_evidence_count:
                    missing.append(
                        f"evidence {len(evidence)}/{criteria.required_evidence_count}"
                    )
                if len(active_theories) < criteria.required_theory_count:
                    missing.append(
                        f"theories {len(active_theories)}/{criteria.required_theory_count}"
                    )
                if criteria.required_theory_min_confidence is not None:
                    minimum = _THEORY_CONFIDENCE_ORDER[criteria.required_theory_min_confidence]
                    if not any(
                        _THEORY_CONFIDENCE_ORDER[theory.confidence] >= minimum
                        for theory in active_theories
                    ):
                        missing.append(
                            f"theory confidence >= {criteria.required_theory_min_confidence.value}"
                        )
                if len(contributors) < criteria.required_distinct_contributors:
                    missing.append(
                        f"distinct contributors {len(contributors)}/"
                        f"{criteria.required_distinct_contributors}"
                    )
                missing_actions = set(criteria.required_actions) - performed_actions
                if missing_actions:
                    missing.append(f"required actions {', '.join(sorted(missing_actions))}")
                if missing:
                    raise DomainError(
                        ErrorCode.INVALID_ACTION,
                        "case resolution criteria not satisfied: " + "; ".join(missing),
                    )

                now = self._clock.now()
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.CASE_CLOSED,
                    created_at=now,
                    executed_at=now,
                    actor=str(actor.id),
                    target=str(case.id),
                    cause="close_case",
                    payload={
                        "case_id": str(case.id),
                        "from": case.status.value,
                        "to": "CLOSED",
                        "resolution_criteria_satisfied": True,
                        "evidence_count": len(evidence),
                        "theory_count": len(active_theories),
                        "distinct_contributors": len(contributors),
                        "performed_actions": sorted(performed_actions),
                    },
                    result="success",
                )
                case.apply(event)
                uow.cases.save(case)
                commit_case_event(uow, instance, expected_version, event)

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "case_id": str(case.id),
                    "status": case.status.value,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)