"""Создание WORLD INSTANCE.

Инстанс и событие ``WORLD_INSTANCE_CREATED`` записываются в одной транзакции:
мира без записи о его создании быть не может.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    Clock,
    EventId,
    WorldInstanceId,
    new_event_id,
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
        new_instance_id: Callable[[], WorldInstanceId] = new_world_instance_id,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_instance_id = new_instance_id
        self._new_event_id = new_event_id_factory

    def handle(self, command: CreateWorldInstanceCommand) -> WorldInstance:
        now = self._clock.now()
        instance = WorldInstance.create(
            id=self._new_instance_id(),
            telegram_chat_id=command.telegram_chat_id,
            seed=command.seed,
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
            },
            result="success",
        )
        # Событие создания фиксируется, но state_version созданного инстанса = 0.
        instance.apply(event)

        with self._uow_factory() as uow:
            uow.world_instances.add(instance)
            uow.events.append(event)
            uow.commit()
        return instance
