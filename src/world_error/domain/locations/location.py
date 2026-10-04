"""Локация: определение (контент) и состояние (инстанс).

``LocationDefinition`` — глобальный неизменяемый шаблон, включая граф связей.
``LocationState`` — то, что принадлежит конкретному WORLD INSTANCE: там хранится
только то, что реально меняется (факт обнаружения локации). Названия, типы и
связи в БД не дублируются (11_WORLD_STATE_V1 §35: один источник истины).

Маршруты пока неизменяемы: блокировка дорог появится вместе с механиками
последствий, тогда состояние маршрута станет частью ``LocationState``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    DiscoveryState,
    DomainError,
    ErrorCode,
    LocationKey,
    WorldInstanceId,
)


@dataclass(frozen=True, slots=True)
class LocationDefinition:
    """Глобальный шаблон локации (content)."""

    key: LocationKey
    name: str
    type: str
    description: str
    connections: frozenset[LocationKey]


@dataclass(slots=True)
class LocationState:
    """Состояние локации внутри конкретного WORLD INSTANCE."""

    world_instance_id: WorldInstanceId
    key: LocationKey
    updated_at: datetime
    discovery_state: DiscoveryState = DiscoveryState.UNDISCOVERED
    first_visited_at: datetime | None = None

    def apply(self, event: Event) -> None:
        """Отметить, что в локации впервые оказался персонаж.

        Событие ``CHARACTER_CREATED`` учитывает стартовую локацию персонажа,
        ``CHARACTER_MOVED`` — локацию назначения. Знание персонажу при этом НЕ
        выдаётся: знание о локации — отдельная механика.
        """
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another world instance: {event.world_instance_id}",
            )
        target_key = self._location_of(event)
        if target_key != self.key:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} targets location {target_key}, not {self.key}",
            )
        occurred_at = event.executed_at or event.created_at
        if self.discovery_state is DiscoveryState.UNDISCOVERED:
            self.discovery_state = DiscoveryState.DISCOVERED
            self.first_visited_at = occurred_at
        self.updated_at = occurred_at

    @staticmethod
    def _location_of(event: Event) -> LocationKey:
        if event.type is EventType.CHARACTER_MOVED:
            return LocationKey(str(event.payload["to"]))
        if event.type is EventType.CHARACTER_CREATED:
            return LocationKey(str(event.payload["location_key"]))
        raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported event type: {event.type}")
