"""Информационный объект мира.

Разделение, которое здесь закреплено:

* ``InformationDefinition.content`` — то, что узнаёт нашедший (claim);
* ``InformationDefinition.truth`` — канонический факт мира. В знание он не
  переносится никогда (MASTER_SPEC §6, 11_WORLD_STATE_V1 §9–§11).

Информация существует в мире независимо от того, нашёл её кто-то или нет
(19_MVP §16 design; 11_WORLD_STATE_V1 §30: EXISTENCE ≠ VISIBILITY ≠ KNOWLEDGE).
Объект создаётся при создании INSTANCE из контента, а обнаружение меняет его
world-состояние на DISCOVERED и создаёт знание у конкретного субъекта.

``discovered_by`` — id субъекта-первооткрывателя: ``ch_...`` (персонаж) или
``npc_...`` (NPC). Префиксы идентификаторов однозначно различают тип, поэтому
отдельная колонка типа не нужна. Первый нашедший не перезаписывается.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    DiscoveryState,
    DomainError,
    ErrorCode,
    InformationId,
    LocationKey,
    WorldInstanceId,
)


@dataclass(frozen=True, slots=True)
class InformationDefinition:
    """Глобальное описание информационного объекта (content)."""

    key: str
    location_key: LocationKey
    information_type: str
    source: str
    authenticity: str
    access: str
    content: str
    truth: str
    document_date: date | None = None


@dataclass(slots=True)
class Information:
    """Конкретный информационный объект внутри WORLD INSTANCE."""

    id: InformationId
    world_instance_id: WorldInstanceId
    key: str
    location_key: LocationKey
    discovery_state: DiscoveryState = DiscoveryState.UNDISCOVERED
    discovered_by: str | None = None
    discovered_at: datetime | None = None
    created_at: datetime | None = None

    def apply(self, event: Event) -> None:
        """Отметить обнаружение объекта в мире.

        Первый нашедший НЕ перезаписывается: повторное обнаружение другим
        субъектом (персонажем или NPC) меняет только знание, но не историю мира.
        """
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another world instance: {event.world_instance_id}",
            )
        if event.type is not EventType.INFORMATION_DISCOVERED:
            raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported event type: {event.type}")
        if str(event.payload.get("information_key")) != self.key:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} targets another information object: {event.payload.get('information_key')}",
            )
        if self.discovery_state is DiscoveryState.UNDISCOVERED:
            self.discovery_state = DiscoveryState.DISCOVERED
            self.discovered_by = str(event.actor) if event.actor else None
            self.discovered_at = event.executed_at or event.created_at
