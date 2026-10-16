"""Перемещение NPC между локациями.

Правила те же, что у персонажа: цель должна быть связана с текущей локацией,
NPC должен быть ACTIVE. Действие идёт через Event Engine, поэтому NPC двигается
без присутствия игроков (05_NPCS §6: NPC не ждут игрока).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    NpcId,
    WorldInstanceId,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class NpcMoveCommand:
    world_instance_id: WorldInstanceId
    npc_id: NpcId
    to_location_key: LocationKey
    cause: str = "npc_move"


class NpcMoveHandler:
    ACTION = "NPC_MOVE"

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

    def handle(self, command: NpcMoveCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                npc = uow.npcs.get(instance.id, command.npc_id)
                npc.ensure_can_act()

                target = self._catalog.location(command.to_location_key)
                from_key = npc.location_key
                if not self._catalog.is_connected(from_key, target.key):
                    raise DomainError(
                        ErrorCode.INVALID_ACTION,
                        f"location {target.key} is not connected to {from_key}",
                    )

                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.NPC_MOVED,
                    created_at=now,
                    executed_at=now,
                    actor=str(npc.id),
                    target=str(target.key),
                    cause=command.cause,
                    payload={"from": str(from_key), "to": str(target.key)},
                    result="success",
                )
                instance.register_applied_event(event)
                npc.apply(event)
                destination = uow.locations.get(instance.id, target.key)
                destination.apply(event)

                uow.npcs.save(npc)
                uow.locations.save(destination)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "npc_id": str(npc.id),
                    "npc_key": npc.key,
                    "from": str(from_key),
                    "to": str(npc.location_key),
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
