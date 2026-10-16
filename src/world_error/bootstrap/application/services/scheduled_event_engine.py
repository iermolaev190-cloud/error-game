"""Deterministic, restart-safe scheduled-event pump; no background worker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

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
    ScheduledEventId,
    WorldInstanceId,
    new_event_id,
)
from world_error.domain.time.scheduled_event import (
    ScheduledEvent,
    ScheduledEventStatus,
    ScheduledTriggerKind,
)
from world_error.domain.time.time_point import TimePoint, TimePointKind
from world_error.domain.world.instance import InstanceLifecycle


@dataclass(frozen=True, slots=True)
class ScheduledPumpOutcome:
    applied: tuple[ScheduledEventId, ...] = ()
    failed: tuple[ScheduledEventId, ...] = ()
    event_ids: tuple[EventId, ...] = ()
    limit_reached: bool = False

    @property
    def steps(self) -> int:
        return len(self.applied) + len(self.failed)

    @property
    def changed(self) -> bool:
        return bool(self.applied or self.failed)


class ScheduledEventEngine:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        catalog: ContentCatalog,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog
        self._clock = clock
        self._new_event_id = new_event_id_factory

    def pump(
        self, world_instance_id: WorldInstanceId, *, max_steps: int
    ) -> ScheduledPumpOutcome:
        applied: list[ScheduledEventId] = []
        failed: list[ScheduledEventId] = []
        event_ids: list[EventId] = []
        while len(applied) + len(failed) < max_steps:
            outcome = self._apply_next_due(world_instance_id)
            if outcome is None:
                break
            scheduled_event_id, event_id, did_apply = outcome
            (applied if did_apply else failed).append(scheduled_event_id)
            event_ids.append(event_id)
        processed = len(applied) + len(failed)
        limit_reached = processed >= max_steps and self.has_due(world_instance_id)
        return ScheduledPumpOutcome(
            applied=tuple(applied),
            failed=tuple(failed),
            event_ids=tuple(event_ids),
            limit_reached=limit_reached,
        )

    def has_due(self, world_instance_id: WorldInstanceId) -> bool:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            if instance.lifecycle is not InstanceLifecycle.ACTIVE:
                return False
            now = self._clock.now()
            world_time = instance.world_time_at(now)
            return any(
                self._is_due(uow, instance.world_tick, world_time, item)
                for item in uow.scheduled_events.list_pending(instance.id)
            )

    def _is_due(self, uow, current_tick: int, world_time, item: ScheduledEvent) -> bool:  # noqa: ANN001
        matching_event_seen = False
        if item.trigger.kind is ScheduledTriggerKind.ON_EVENT_TYPE:
            matching_event_seen = uow.events.has_event_of_type_since(
                item.world_instance_id,
                item.trigger.event_type,
                item.created_event_id,
            )
        return item.trigger.is_due(
            current_tick=current_tick,
            current_time=world_time,
            matching_event_seen=matching_event_seen,
        )

    def _apply_next_due(
        self, world_instance_id: WorldInstanceId
    ) -> tuple[ScheduledEventId, EventId, bool] | None:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            if instance.lifecycle is not InstanceLifecycle.ACTIVE:
                return None
            now = self._clock.now()
            world_time = instance.world_time_at(now)
            due = next(
                (
                    item
                    for item in uow.scheduled_events.list_pending(instance.id)
                    if self._is_due(uow, instance.state.world_tick, world_time, item)
                ),
                None,
            )
            scheduled_event_id = None if due is None else due.id
        if scheduled_event_id is None:
            return None
        return self._apply_one(world_instance_id, scheduled_event_id)

    def _apply_one(
        self, world_instance_id: WorldInstanceId, scheduled_event_id: ScheduledEventId
    ) -> tuple[ScheduledEventId, EventId, bool] | None:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            if instance.lifecycle is not InstanceLifecycle.ACTIVE:
                return None
            scheduled = uow.scheduled_events.get(instance.id, scheduled_event_id)
            now = self._clock.now()
            if not self._is_due(uow, instance.state.world_tick, instance.world_time_at(now), scheduled):
                return None
            expected_version = instance.state.state_version
            event_id = self._new_event_id()
            event = Event(
                id=event_id,
                world_instance_id=instance.id,
                type=EventType.SCHEDULED_EVENT_TRIGGERED,
                created_at=now,
                executed_at=now,
                actor="system",
                target=scheduled.event_key,
                cause=f"scheduled:{scheduled.id}",
                payload={
                    "scheduled_event_id": str(scheduled.id),
                    "cause_event_id": str(scheduled.cause_event_id),
                    "event_key": scheduled.event_key,
                    "event_payload": dict(scheduled.payload),
                },
                result="success",
            ).with_time_point(
                TimePoint(
                    event_id=event_id,
                    kind=TimePointKind.OCCURRED_AT,
                    at=instance.world_time_at(now),
                )
            )
            arrival = None
            if scheduled.event_key == "CHARACTER_ARRIVAL":
                try:
                    arrival = self._build_character_arrival(uow, instance, scheduled, now)
                except DomainError as exc:
                    failed_event = Event(
                        id=event_id,
                        world_instance_id=instance.id,
                        type=EventType.SCHEDULED_EVENT_FAILED,
                        created_at=now,
                        executed_at=now,
                        actor="system",
                        target=str(scheduled.id),
                        cause=f"scheduled:{scheduled.id}",
                        payload={
                            "scheduled_event_id": str(scheduled.id),
                            "event_key": scheduled.event_key,
                            "error_code": exc.code.value,
                            "reason": exc.message,
                        },
                        result="failed",
                    )
                    scheduled.mark_failed(event_id=failed_event.id, now=now)
                    instance.register_applied_event(failed_event)
                    uow.events.append(failed_event)
                    uow.scheduled_events.save(scheduled)
                    uow.world_instances.save(instance, expected_state_version=expected_version)
                    uow.commit()
                    return scheduled.id, failed_event.id, False

            event = event.with_time_point(
                TimePoint(
                    event_id=event.id,
                    kind=TimePointKind.OCCURRED_AT,
                    at=instance.world_time_at(now),
                )
            )
            scheduled.mark_applied(event_id=event.id, now=now)
            instance.register_applied_event(event)
            uow.events.append(event)
            if arrival is not None:
                character, destination, movement = arrival
                character.apply(movement)
                destination.apply(movement)
                instance.register_applied_event(movement)
                uow.characters.save(character)
                uow.locations.save(destination)
                uow.events.append(movement)
            uow.scheduled_events.save(scheduled)
            uow.world_instances.save(instance, expected_state_version=expected_version)
            uow.commit()
            return scheduled.id, event.id, True

    def _build_character_arrival(
        self, uow, instance, scheduled: ScheduledEvent, now  # noqa: ANN001
    ):
        character_id = scheduled.payload.get("character_id")
        target_key = scheduled.payload.get("to_location_key")
        if not character_id or not target_key:
            raise DomainError(ErrorCode.INVALID_ACTION, "CHARACTER_ARRIVAL requires character_id and to_location_key")
        character = uow.characters.get(instance.id, CharacterId(str(character_id)))
        character.ensure_can_act()
        target = self._catalog.location(LocationKey(str(target_key)))
        if not self._catalog.is_connected(character.location_key, target.key):
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"arrival target {target.key} is not connected to {character.location_key}",
            )
        destination = uow.locations.get(instance.id, target.key)
        movement = Event(
            id=self._new_event_id(),
            world_instance_id=instance.id,
            type=EventType.CHARACTER_MOVED,
            created_at=now,
            executed_at=now,
            actor=str(character.id),
            target=str(target.key),
            cause=f"scheduled:{scheduled.id}",
            payload={"from": str(character.location_key), "to": str(target.key)},
            result="success",
        )
        return character, destination, movement
