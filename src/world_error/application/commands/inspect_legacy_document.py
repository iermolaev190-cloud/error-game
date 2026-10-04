"""Discover a legacy document through the world, never through account linkage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    LegacyDocumentId,
    WorldInstanceId,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class InspectLegacyDocumentCommand:
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    document_id: LegacyDocumentId


class InspectLegacyDocumentHandler:
    ACTION = "INSPECT"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def handle(self, command: InspectLegacyDocumentCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                character = uow.characters.get(instance.id, command.character_id)
                character.ensure_can_act()
                document = uow.legacy_documents.get(instance.id, command.document_id)
                if character.location_key != document.location_key:
                    raise DomainError(
                        ErrorCode.NOT_ALLOWED,
                        "legacy document is not at the character's current location",
                    )
                prior = next(
                    (
                        event
                        for event in uow.events.list_for_instance(instance.id)
                        if event.type is EventType.LEGACY_DOCUMENT_DISCOVERED
                        and event.actor == str(character.id)
                        and event.target == str(document.id)
                    ),
                    None,
                )
                if prior is not None:
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "already_known": True,
                            "document_id": str(document.id),
                            "document_key": document.document_key,
                            "content": document.content,
                        },
                    )

                expected_version = instance.state.state_version
                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.LEGACY_DOCUMENT_DISCOVERED,
                    created_at=now,
                    executed_at=now,
                    actor=str(character.id),
                    target=str(document.id),
                    cause=f"event:{document.created_event_id}",
                    payload={
                        "document_id": str(document.id),
                        "document_key": document.document_key,
                        "content": document.content,
                        "created_by_character_id": str(document.created_by_character_id),
                    },
                    result="success",
                )
                instance.register_applied_event(event)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()
            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "already_known": False,
                    "document_id": str(document.id),
                    "document_key": document.document_key,
                    "content": document.content,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
