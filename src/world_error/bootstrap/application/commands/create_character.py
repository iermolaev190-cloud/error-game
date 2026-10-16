"""Создание персонажа в WORLD INSTANCE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.characters.character import Character
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    WorldInstanceId,
    new_character_id,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class CreateCharacterCommand:
    world_instance_id: WorldInstanceId
    player_id: str
    name: str
    location_key: LocationKey | None = None
    actor: str = "system"


class CreateCharacterHandler:
    """Один аккаунт = один живой персонаж в конкретном WORLD INSTANCE (14_MULTIPLAYER_V1 §5)."""

    ACTION = "CREATE_CHARACTER"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        catalog: ContentCatalog,
        new_character_id_factory: Callable[[], CharacterId] = new_character_id,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._catalog = catalog
        self._new_character_id = new_character_id_factory
        self._new_event_id = new_event_id_factory

    def handle(self, command: CreateCharacterCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                start_key = command.location_key or self._catalog.start_location
                self._catalog.location(start_key)  # NOT_FOUND, если локация неизвестна

                existing = uow.characters.find_alive_by_player(instance.id, command.player_id)
                if existing is not None:
                    raise DomainError(
                        ErrorCode.NOT_ALLOWED,
                        f"player {command.player_id} already has an alive character "
                        f"in this world: {existing.id}",
                    )

                now = self._clock.now()
                character = Character.create(
                    id=self._new_character_id(),
                    world_instance_id=instance.id,
                    player_id=command.player_id,
                    name=command.name,
                    location_key=start_key,
                    now=now,
                )
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.CHARACTER_CREATED,
                    created_at=now,
                    executed_at=now,
                    actor=str(character.id),
                    target=str(character.id),
                    cause="create_character",
                    payload={
                        "player_id": command.player_id,
                        "name": command.name,
                        "location_key": str(start_key),
                    },
                    result="success",
                )
                instance.register_applied_event(event)
                character.apply(event)
                # Персонаж физически находится в стартовой локации — мир это фиксирует.
                start_location = uow.locations.get(instance.id, start_key)
                start_location.apply(event)

                uow.characters.add(character)
                uow.locations.save(start_location)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "character_id": str(character.id),
                    "world_instance_id": str(instance.id),
                    "player_id": character.player_id,
                    "name": character.name,
                    "location_key": str(character.location_key),
                    "lifecycle": character.lifecycle.value,
                    "activity": character.activity.value,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
