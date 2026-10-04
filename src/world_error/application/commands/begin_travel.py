"""Start travel now and resolve arrival later through a scheduled event."""

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
    ScheduledEventId,
    WorldInstanceId,
    new_event_id,
    new_scheduled_event_id,
)
from world_error.domain.time.action_cost import CostTicks
from world_error.domain.time.scheduled_event import (
    ScheduledEvent,
    ScheduledEventTrigger,
    ScheduledTriggerKind,
)


@dataclass(frozen=True, slots=True)
class BeginTravelCommand:
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    to_location_key: str
    cost_ticks: CostTicks
    idempotency_key: str


class BeginTravelHandler:
    ACTION = "BEGIN_TRAVEL"

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        catalog: ContentCatalog,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_scheduled_event_id_factory: Callable[[], ScheduledEventId] = new_scheduled_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_scheduled_event_id = new_scheduled_event_id_factory

    def handle(self, command: BeginTravelCommand) -> ActionResult:
        try:
            cost = CostTicks(int(command.cost_ticks))
            if not command.idempotency_key.strip():
                raise DomainError(ErrorCode.INVALID_ACTION, "travel idempotency key is required")
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                character = uow.characters.get(instance.id, command.character_id)
                character.ensure_can_act()
                target = self._catalog.location(command.to_location_key)
                if not self._catalog.is_connected(character.location_key, target.key):
                    raise DomainError(
                        ErrorCode.INVALID_ACTION,
                        f"location {target.key} is not connected to {character.location_key}",
                    )

                effect_payload = {
                    "character_id": str(character.id),
                    "to_location_key": str(target.key),
                }
                existing = uow.scheduled_events.find_by_idempotency_key(
                    instance.id, command.idempotency_key
                )
                if existing is not None:
                    if existing.event_key != "CHARACTER_ARRIVAL" or dict(existing.payload) != effect_payload:
                        raise DomainError(
                            ErrorCode.ALREADY_PROCESSED,
                            f"travel idempotency key reused: {command.idempotency_key}",
                        )
                    return ActionResult.success(
                        self.ACTION,
                        event_ids=(existing.created_event_id,),
                        payload={
                            "scheduled_event_id": str(existing.id),
                            "status": existing.status.value,
                            "already_started": True,
                        },
                    )

                expected_version = instance.state.state_version
                now = self._clock.now()
                start_tick = instance.state.world_tick
                scheduled_id = self._new_scheduled_event_id()
                travel_event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.TRAVEL_STARTED,
                    created_at=now,
                    executed_at=now,
                    actor=str(character.id),
                    target=str(target.key),
                    cause="begin_travel",
                    payload={
                        "character_id": str(character.id),
                        "from": str(character.location_key),
                        "to": str(target.key),
                        "cost_ticks": int(cost),
                        "scheduled_event_id": str(scheduled_id),
                    },
                    result="success",
                )
                scheduled = ScheduledEvent(
                    id=scheduled_id,
                    world_instance_id=instance.id,
                    cause_event_id=travel_event.id,
                    created_event_id=travel_event.id,
                    idempotency_key=command.idempotency_key,
                    trigger=ScheduledEventTrigger(
                        kind=ScheduledTriggerKind.AT_TICK,
                        due_tick=start_tick + int(cost),
                    ),
                    event_key="CHARACTER_ARRIVAL",
                    payload=effect_payload,
                    created_at=now,
                )
                instance.register_applied_event(travel_event)
                cost_event = consume_action_cost(
                    instance,
                    action=self.ACTION,
                    action_event=travel_event,
                    cost=cost,
                    now=now,
                    new_event_id_factory=self._new_event_id,
                )
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(travel_event)
                if cost_event is not None:
                    uow.events.append(cost_event)
                uow.scheduled_events.add(scheduled)
                uow.commit()
            return ActionResult.success(
                self.ACTION,
                event_ids=(travel_event.id,) + (() if cost_event is None else (cost_event.id,)),
                payload={
                    "scheduled_event_id": str(scheduled_id),
                    "status": "PENDING",
                    "from": str(character.location_key),
                    "to": str(target.key),
                    "cost_ticks": int(cost),
                    "due_tick": scheduled.trigger.due_tick,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)