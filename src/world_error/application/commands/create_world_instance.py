"""Создание WORLD INSTANCE.

Инстанс, его instance-состояние и событие ``WORLD_INSTANCE_CREATED``
записываются в одной транзакции: мира без записи о его создании быть не может.

При создании мира из контента материализуется instance-состояние:
* ``LocationState`` для каждой локации (UNDISCOVERED);
* ``Information`` для каждого информационного объекта (UNDISCOVERED).

Информация существует в мире независимо от того, нашёл её кто-то или нет
(19_MVP §16 design), поэтому она создаётся здесь, а не в момент INSPECT.
Материализация — часть создания мира, поэтому отдельного события не требует:
её покрывает ``WORLD_INSTANCE_CREATED``, и ``state_version`` остаётся 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.information.information import Information
from world_error.domain.locations.location import LocationState
from world_error.domain.shared.kernel import (
    Clock,
    EventId,
    InformationId,
    WorldInstanceId,
    new_event_id,
    new_information_id,
    new_world_instance_id,
)
from world_error.domain.world.instance import InstanceEnvironment, WorldInstance


@dataclass(frozen=True, slots=True)
class CreateWorldInstanceCommand:
    telegram_chat_id: int
    seed: int
    environment: InstanceEnvironment = InstanceEnvironment.DEV
    actor: str = "system"


class CreateWorldInstanceHandler:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        catalog: ContentCatalog,
        new_instance_id: Callable[[], WorldInstanceId] = new_world_instance_id,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_information_id_factory: Callable[[], InformationId] = new_information_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._catalog = catalog
        self._new_instance_id = new_instance_id
        self._new_event_id = new_event_id_factory
        self._new_information_id = new_information_id_factory

    def handle(self, command: CreateWorldInstanceCommand) -> WorldInstance:
        now = self._clock.now()
        instance = WorldInstance.create(
            id=self._new_instance_id(),
            telegram_chat_id=command.telegram_chat_id,
            seed=command.seed,
            content_version=self._catalog.version,
            environment=command.environment,
            now=now,
        )
        event = Event(
            id=self._new_event_id(),
            world_instance_id=instance.id,
            type=EventType.WORLD_INSTANCE_CREATED,
            created_at=now,
            executed_at=now,
            actor=command.actor,
            target=str(instance.id),
            cause="create_world_instance",
            payload={
                "telegram_chat_id": command.telegram_chat_id,
                "seed": command.seed,
                "environment": command.environment.value,
                "content_version": self._catalog.version,
            },
            result="success",
        )
        # Событие создания фиксируется, но state_version созданного инстанса = 0.
        instance.apply(event)

        with self._uow_factory() as uow:
            uow.world_instances.add(instance)
            for location_definition in self._catalog.locations.values():
                uow.locations.add(
                    LocationState(
                        world_instance_id=instance.id,
                        key=location_definition.key,
                        updated_at=now,
                    )
                )
            for information_definition in self._catalog.information.values():
                uow.information.add(
                    Information(
                        id=self._new_information_id(),
                        world_instance_id=instance.id,
                        key=information_definition.key,
                        location_key=information_definition.location_key,
                        created_at=now,
                    )
                )
            uow.events.append(event)
            uow.commit()
        return instance
