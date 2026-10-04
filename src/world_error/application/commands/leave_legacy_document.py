"""Leave a posthumous document in the world, outside character inventory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.characters.character import CharacterLifecycle
from world_error.domain.events.event import Event, EventType
from world_error.domain.legacy.legacy_document import LegacyDocument
from world_error.domain.shared.kernel import (
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    LegacyDocumentId,
    WorldInstanceId,
    new_event_id,
    new_legacy_document_id,
)


@dataclass(frozen=True, slots=True)
class LeaveLegacyDocumentCommand:
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    document_key: str
    content: str


class LeaveLegacyDocumentHandler:
    ACTION = "LEAVE_LEGACY_DOCUMENT"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_document_id_factory: Callable[[], LegacyDocumentId] = new_legacy_document_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_document_id = new_document_id_factory

    def handle(self, command: LeaveLegacyDocumentCommand) -> ActionResult:
        try:
            if not command.document_key.strip() or not command.content.strip():
                raise DomainError(ErrorCode.INVALID_ACTION, "legacy document key and content are required")
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                character = uow.characters.get(instance.id, command.character_id)
                if character.lifecycle is not CharacterLifecycle.DEAD:
                    raise DomainError(
                        ErrorCode.NOT_ALLOWED,
                        "legacy document can only be left for a deceased character",
                    )
                if character.death_event_id is None or character.death_cause_event_id is None:
                    raise DomainError(ErrorCode.INVALID_ACTION, "dead character has no death provenance")
                uow.events.get(instance.id, character.death_event_id)
                expected_version = instance.state.state_version
                now = self._clock.now()
                document_id = self._new_document_id()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.LEGACY_DOCUMENT_LEFT,
                    created_at=now,
                    executed_at=now,
                    actor=str(character.id),
                    target=str(document_id),
                    cause=f"event:{character.death_event_id}",
                    payload={
                        "document_id": str(document_id),
                        "document_key": command.document_key,
                        "location_key": str(character.location_key),
                        "created_by_character_id": str(character.id),
                        "death_event_id": str(character.death_event_id),
                    },
                    result="success",
                )
                document = LegacyDocument(
                    id=document_id,
                    world_instance_id=instance.id,
                    document_key=command.document_key,
                    location_key=character.location_key,
                    created_by_character_id=character.id,
                    death_event_id=character.death_event_id,
                    created_event_id=event.id,
                    content=command.content,
                    created_at=now,
                )
                instance.register_applied_event(event)
                uow.events.append(event)
                uow.legacy_documents.add(document)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.commit()
            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={"document_id": str(document_id), "location_key": str(document.location_key)},
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
