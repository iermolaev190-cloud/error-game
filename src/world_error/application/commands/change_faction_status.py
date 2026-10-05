"""Change faction status through FACTION_STATUS_CHANGED."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.factions.faction import FactionStatus
from world_error.domain.shared.kernel import (
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    FactionId,
    WorldInstanceId,
    new_event_id,
)


@dataclass(frozen=True, slots=True)
class ChangeFactionStatusCommand:
    world_instance_id: WorldInstanceId
    faction_id: FactionId
    to_status: FactionStatus | str
    cause: str = "faction_status"


class ChangeFactionStatusHandler:
    ACTION = "FACTION_STATUS"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def handle(self, command: ChangeFactionStatusCommand) -> ActionResult:
        try:
            try:
                target = FactionStatus(command.to_status)
            except ValueError as exc:
                raise DomainError(ErrorCode.INVALID_ACTION, "unknown faction status") from exc

            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                faction = uow.factions.get(instance.id, command.faction_id)
                if faction.status is target:
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "changed": False,
                            "faction_id": str(faction.id),
                            "status": faction.status.value,
                        },
                    )

                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.FACTION_STATUS_CHANGED,
                    created_at=now,
                    executed_at=now,
                    actor=str(faction.id),
                    target=str(faction.id),
                    cause=command.cause,
                    payload={"from": faction.status.value, "to": target.value},
                    result="success",
                )
                instance.register_applied_event(event)
                faction.apply(event)

                uow.factions.save(faction)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "changed": True,
                    "faction_id": str(faction.id),
                    "from": event.payload["from"],
                    "to": faction.status.value,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)