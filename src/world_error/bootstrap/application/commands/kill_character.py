"""Apply a character death atomically from a verified world cause event."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.characters.character import CharacterLifecycle
from world_error.domain.death.death import DeathEvent
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class KillCharacterCommand:
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    cause_event_id: EventId
    death_event_id: EventId | None = None
    actor: str = "world"


class KillCharacterHandler:
    ACTION = "KILL_CHARACTER"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def handle(self, command: KillCharacterCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                character = uow.characters.get(instance.id, command.character_id)
                if not str(command.cause_event_id).strip():
                    raise DomainError(ErrorCode.INVALID_ACTION, "death requires a cause event")
                death_event_id = command.death_event_id or self._new_event_id()
                if uow.events.has_event(instance.id, death_event_id):
                    raise DomainError(
                        ErrorCode.ALREADY_PROCESSED,
                        f"death event already processed: {death_event_id}",
                    )
                if character.lifecycle is CharacterLifecycle.DEAD:
                    raise DomainError(
                        ErrorCode.ALREADY_PROCESSED,
                        f"character already dead: {character.id}",
                    )
                if command.cause_event_id == death_event_id:
                    raise DomainError(ErrorCode.INVALID_ACTION, "death event cannot cause itself")
                uow.events.get(instance.id, command.cause_event_id)
                expected_version = instance.state.state_version
                now = self._clock.now()
                event = Event(
                    id=death_event_id,
                    world_instance_id=instance.id,
                    type=EventType.DEATH_EVENT,
                    created_at=now,
                    executed_at=now,
                    actor=command.actor,
                    target=str(character.id),
                    cause=f"event:{command.cause_event_id}",
                    payload={
                        "character_id": str(character.id),
                        "cause_event_id": str(command.cause_event_id),
                    },
                    result="success",
                )
                death = DeathEvent.from_event(event)
                character.apply(event)
                instance.register_applied_event(event)
                uow.events.append(event)
                uow.characters.save(character)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.commit()
            return ActionResult.success(
                self.ACTION,
                event_ids=(death.id,),
                payload={
                    "character_id": str(death.character_id),
                    "death_event_id": str(death.id),
                    "death_cause_event_id": str(death.cause_event_id),
                    "lifecycle": CharacterLifecycle.DEAD.value,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
