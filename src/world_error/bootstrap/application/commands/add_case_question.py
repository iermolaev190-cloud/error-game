"""Append a player-authored question and update the case's current question."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._case_utils import commit_case_event, load_open_case
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.investigations.case import CaseQuestion
from world_error.domain.shared.kernel import (
    CaseId,
    CaseQuestionId,
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
    new_case_question_id,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class AddCaseQuestionCommand:
    world_instance_id: WorldInstanceId
    case_id: CaseId
    added_by: CharacterId
    text: str


class AddCaseQuestionHandler:
    ACTION = "ADD_CASE_QUESTION"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_question_id_factory: Callable[[], CaseQuestionId] = new_case_question_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_question_id = new_question_id_factory

    def handle(self, command: AddCaseQuestionCommand) -> ActionResult:
        try:
            if not command.text.strip():
                raise DomainError(ErrorCode.INVALID_ACTION, "case question must not be empty")
            with self._uow_factory() as uow:
                instance, expected_version, case, actor = load_open_case(
                    uow, command.world_instance_id, command.case_id, command.added_by
                )
                now = self._clock.now()
                question = CaseQuestion(
                    id=self._new_question_id(),
                    world_instance_id=instance.id,
                    case_id=case.id,
                    text=command.text,
                    added_by=actor.id,
                    created_at=now,
                )
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.CASE_QUESTION_ADDED,
                    created_at=now,
                    executed_at=now,
                    actor=str(actor.id),
                    target=str(case.id),
                    cause="add_case_question",
                    payload={
                        "case_id": str(case.id),
                        "question_id": str(question.id),
                        "previous_question": case.current_question,
                        "text": question.text,
                        "added_by": str(actor.id),
                    },
                    result="success",
                )
                case.apply(event)
                uow.cases.add_question(question)
                uow.cases.save(case)
                commit_case_event(uow, instance, expected_version, event)

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={"case_id": str(case.id), "question_id": str(question.id), "text": question.text},
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)