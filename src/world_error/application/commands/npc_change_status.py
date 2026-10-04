"""NPC исчезает или возвращается — событие NPC_STATUS_CHANGED.

Исчезновение не равно смерти (05_NPCS §22): ACTIVE → MISSING и обратно.
``DEAD`` появится вместе с механикой смерти, ``UNKNOWN``/``FOUND`` — позже.
Смена на тот же статус — успешный no-op без события.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.npcs.npc import NpcStatus
from world_error.domain.shared.kernel import (
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    NpcId,
    WorldInstanceId,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class NpcChangeStatusCommand:
    world_instance_id: WorldInstanceId
    npc_id: NpcId
    to_status: NpcStatus | str
    cause: str = "npc_status"


class NpcChangeStatusHandler:
    ACTION = "NPC_STATUS"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def handle(self, command: NpcChangeStatusCommand) -> ActionResult:
        try:
            target = NpcStatus(command.to_status)
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                npc = uow.npcs.get(instance.id, command.npc_id)

                if npc.status is target:
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "changed": False,
                            "npc_id": str(npc.id),
                            "status": npc.status.value,
                            "location_key": str(npc.location_key),
                        },
                    )

                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.NPC_STATUS_CHANGED,
                    created_at=now,
                    executed_at=now,
                    actor=str(npc.id),
                    target=str(npc.id),
                    cause=command.cause,
                    payload={"from": npc.status.value, "to": target.value},
                    result="success",
                )
                instance.register_applied_event(event)
                npc.apply(event)

                uow.npcs.save(npc)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "changed": True,
                    "npc_id": str(npc.id),
                    "from": event.payload["from"],
                    "to": npc.status.value,
                    "location_key": str(npc.location_key),
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
