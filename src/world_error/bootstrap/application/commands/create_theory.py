"""Create a case-specific theory; personal Knowledge remains separate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._case_utils import commit_case_event, load_open_case
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.investigations.case import (
    CaseTheory,
    CaseTheoryConfidence,
    CaseVisibility,
)
from world_error.domain.shared.kernel import (
    CaseId,
    CaseTheoryId,
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
    new_case_theory_id,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class CreateTheoryCommand:
    world_instance_id: WorldInstanceId
    case_id: CaseId
    author_id: CharacterId
    claim: str
    confidence: CaseTheoryConfidence = CaseTheoryConfidence.SPECULATIVE
    visibility: CaseVisibility = CaseVisibility.PRIVATE


class CreateTheoryHandler:
    ACTION = "CREATE_CASE_THEORY"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_theory_id_factory: Callable[[], CaseTheoryId] = new_case_theory_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_theory_id = new_theory_id_factory

    def handle(self, command: CreateTheoryCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance, expected_version, case, author = load_open_case(
                    uow, command.world_instance_id, command.case_id, command.author_id
                )
                now = self._clock.now()
                theory = CaseTheory.create(
                    id=self._new_theory_id(),
                    world_instance_id=instance.id,
                    case_id=case.id,
                    author_id=author.id,
                    claim=command.claim,
                    confidence=command.confidence,
                    visibility=command.visibility,
                    now=now,
                )
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.THEORY_CREATED,
                    created_at=now,
                    executed_at=now,
                    actor=str(author.id),
                    target=str(theory.id),
                    cause="create_case_theory",
                    payload={
                        "case_id": str(case.id),
                        "theory_id": str(theory.id),
                        "author_id": str(author.id),
                        "claim": theory.claim,
                        "confidence": theory.confidence.value,
                        "visibility": theory.visibility.value,
                        "status": theory.status.value,
                    },
                    result="success",
                )
                uow.cases.add_theory(theory)
                commit_case_event(uow, instance, expected_version, event)

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "case_id": str(case.id),
                    "theory_id": str(theory.id),
                    "status": theory.status.value,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)