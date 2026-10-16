"""Перемещение персонажа между локациями."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._action_cost import consume_action_cost
from world_error.application.ports.repositories import UnitOfWorkFactory
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
    new_event_id,
)
from world_error.domain.time.action_cost import CostTicks


@dataclass(frozen=True, slots=True)
class MoveCharacterCommand:
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    to_location_key: LocationKey
    cost_ticks: CostTicks | int | None = None
    cause: str = "move"


class MoveCharacterHandler:
    """MOVE: валидация по графу локаций и один тик мира в одной транзакции.

    Валидация:
    * локация-цель должна существовать в контенте → ``NOT_FOUND``;
    * цель должна быть связана с текущей локацией → ``INVALID_ACTION``
      (жёсткое требование коммита 2);
    * персонаж должен быть жив и активен → ``NOT_ALLOWED``.

    MOVE не выдаёт знание о локации: знание — отдельная механика. Мир лишь
    отмечает, что в локации побывал персонаж (``LocationState.discovery_state``).
    """

    ACTION = "MOVE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        catalog: ContentCatalog,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._catalog = catalog
        self._new_event_id = new_event_id_factory

    def handle(self, command: MoveCharacterCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                character = uow.characters.get(instance.id, command.character_id)
                character.ensure_can_act()

                target = self._catalog.location(command.to_location_key)
                from_key = character.location_key
                if not self._catalog.is_connected(from_key, target.key):
                    raise DomainError(
                        ErrorCode.INVALID_ACTION,
                        f"location {target.key} is not connected to {from_key}",
                    )

                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.CHARACTER_MOVED,
                    created_at=now,
                    executed_at=now,
                    actor=str(character.id),
                    target=str(target.key),
                    cause=command.cause,
                    payload={"from": str(from_key), "to": str(target.key)},
                    result="success",
                )
                instance.register_applied_event(event)
                character.apply(event)
                destination = uow.locations.get(instance.id, target.key)
                destination.apply(event)
                cost_event = consume_action_cost(
                    instance,
                    action=self.ACTION,
                    action_event=event,
                    cost=command.cost_ticks,
                    now=now,
                    new_event_id_factory=self._new_event_id,
                )

                uow.characters.save(character)
                uow.locations.save(destination)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                if cost_event is not None:
                    uow.events.append(cost_event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,) + (() if cost_event is None else (cost_event.id,)),
                payload={
                    "character_id": str(character.id),
                    "from": str(from_key),
                    "to": str(character.location_key),
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                    "cost_ticks": None if command.cost_ticks is None else int(command.cost_ticks),
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
