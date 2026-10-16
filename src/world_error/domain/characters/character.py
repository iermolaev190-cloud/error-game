"""Персонаж игрока внутри WORLD INSTANCE.

Две независимые оси (решение коммита 2):

* ``CharacterLifecycle`` — жив персонаж или мёртв (ALIVE / DEAD);
* ``CharacterActivity`` — доступен ли он как действующий субъект
  (ACTIVE / INACTIVE / UNAVAILABLE / MISSING).

Ось активности не заменяет жизненный цикл и наоборот: мёртвый персонаж не
действует, даже если activity формально ACTIVE.

``player_id`` — непрозрачный идентификатор из интерфейса. Сущность ``Player``
появится отдельной фазой; при этом ``Player ≠ Character`` уже сейчас: один
player_id может иметь персонажей в разных INSTANCE, и они не связаны.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    WorldInstanceId,
)


class CharacterLifecycle(StrEnum):
    ALIVE = "ALIVE"
    DEAD = "DEAD"


class CharacterActivity(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNAVAILABLE = "UNAVAILABLE"
    MISSING = "MISSING"


@dataclass(slots=True)
class Character:
    id: CharacterId
    world_instance_id: WorldInstanceId
    player_id: str
    name: str
    lifecycle: CharacterLifecycle
    activity: CharacterActivity
    location_key: LocationKey
    created_at: datetime
    updated_at: datetime
    death_event_id: EventId | None = None
    death_cause_event_id: EventId | None = None

    def __post_init__(self) -> None:
        has_death_references = self.death_event_id is not None and self.death_cause_event_id is not None
        if self.lifecycle is CharacterLifecycle.DEAD and not has_death_references:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                "DEAD character requires death_event_id and death_cause_event_id",
            )
        if self.lifecycle is CharacterLifecycle.ALIVE and (
            self.death_event_id is not None or self.death_cause_event_id is not None
        ):
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                "ALIVE character cannot have death event references",
            )

    @classmethod
    def create(
        cls,
        *,
        id: CharacterId,
        world_instance_id: WorldInstanceId,
        player_id: str,
        name: str,
        location_key: LocationKey,
        now: datetime,
    ) -> "Character":
        return cls(
            id=id,
            world_instance_id=world_instance_id,
            player_id=player_id,
            name=name,
            lifecycle=CharacterLifecycle.ALIVE,
            activity=CharacterActivity.ACTIVE,
            location_key=location_key,
            created_at=now,
            updated_at=now,
        )

    def can_act(self) -> bool:
        """Мёртвый персонаж не выполняет обычные физические действия."""
        return self.lifecycle is CharacterLifecycle.ALIVE and self.activity is CharacterActivity.ACTIVE

    def ensure_can_act(self) -> None:
        if not self.can_act():
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"character {self.id} cannot act: lifecycle={self.lifecycle}, activity={self.activity}",
            )

    def apply(self, event: Event) -> None:
        """Применить событие персонажа."""
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another world instance: {event.world_instance_id}",
            )
        if event.type is EventType.CHARACTER_MOVED:
            if event.actor != str(self.id):
                raise DomainError(
                    ErrorCode.NOT_ALLOWED,
                    f"event {event.id} belongs to another character: {event.actor}",
                )
            self.location_key = LocationKey(str(event.payload["to"]))
            self.updated_at = event.executed_at or event.created_at
            return
        if event.type is EventType.CHARACTER_CREATED:
            # Персонаж создан фабрикой: событие фиксирует факт, состояние уже задано.
            return
        if event.type is EventType.DEATH_EVENT:
            cause_event_id = event.payload.get("cause_event_id")
            if event.target != str(self.id) or event.payload.get("character_id") != str(self.id):
                raise DomainError(
                    ErrorCode.NOT_ALLOWED,
                    f"death event {event.id} targets another character",
                )
            if not cause_event_id:
                raise DomainError(ErrorCode.INVALID_ACTION, "death event requires a cause event")
            if event.id == EventId(str(cause_event_id)):
                raise DomainError(ErrorCode.INVALID_ACTION, "death event cannot cause itself")
            if self.lifecycle is CharacterLifecycle.DEAD:
                raise DomainError(ErrorCode.ALREADY_PROCESSED, f"character {self.id} is already dead")
            self.lifecycle = CharacterLifecycle.DEAD
            self.death_event_id = event.id
            self.death_cause_event_id = EventId(str(cause_event_id))
            self.updated_at = event.executed_at or event.created_at
            return
        raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported event type: {event.type}")
