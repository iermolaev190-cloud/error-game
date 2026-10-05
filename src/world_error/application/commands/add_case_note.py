"""Append a private or case-shared note."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._case_utils import commit_case_event, load_open_case
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.investigations.case import CaseNote, CaseNoteVisibility
from world_error.domain.shared.kernel import (
    CaseId,
    CaseNoteId,
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
    new_case_note_id,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class AddCaseNoteCommand:
    world_instance_id: WorldInstanceId
    case_id: CaseId
    author_id: CharacterId
    text: str
    visibility: CaseNoteVisibility = CaseNoteVisibility.PRIVATE


class AddCaseNoteHandler:
    ACTION = "ADD_CASE_NOTE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_note_id_factory: Callable[[], CaseNoteId] = new_case_note_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_note_id = new_note_id_factory

    def handle(self, command: AddCaseNoteCommand) -> ActionResult:
        try:
            if not command.text.strip():
                raise DomainError(ErrorCode.INVALID_ACTION, "case note must not be empty")
            with self._uow_factory() as uow:
                instance, expected_version, case, author = load_open_case(
                    uow, command.world_instance_id, command.case_id, command.author_id
                )
                now = self._clock.now()
                note = CaseNote(
                    id=self._new_note_id(),
                    world_instance_id=instance.id,
                    case_id=case.id,
                    author_id=author.id,
                    text=command.text,
                    visibility=command.visibility,
                    created_at=now,
                )
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.CASE_NOTE_ADDED,
                    created_at=now,
                    executed_at=now,
                    actor=str(author.id),
                    target=str(note.id),
                    cause="add_case_note",
                    payload={
                        "case_id": str(case.id),
                        "note_id": str(note.id),
                        "author_id": str(author.id),
                        "visibility": note.visibility.value,
                    },
                    result="success",
                )
                uow.cases.add_note(note)
                commit_case_event(uow, instance, expected_version, event)

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "case_id": str(case.id),
                    "note_id": str(note.id),
                    "visibility": note.visibility.value,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)