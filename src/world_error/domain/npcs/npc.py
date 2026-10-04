"""NPC — субъект мира, а не интерфейс для выдачи контента (05_NPCS §35).

Модель коммита 4 намеренно узкая:

* определение (имя, описание, цели, стартовая локация) — контент, immutable;
* состояние (локация, статус) — instance-scoped и меняется только событиями;
* знание NPC живёт в общей таблице ``knowledge`` с ``subject_type = NPC``
  (см. domain/knowledge), а «память» NPC = его записи знания + журнал событий,
  где он был actor/target. Отдельной таблицы памяти нет.

Что сознательно не входит: расписания (05_NPCS §23), отношения и память об
игроках (§13, §29), экономика (§30), смерть (§21) — это следующие фазы.

Статусы: ``ACTIVE`` и ``MISSING`` (05_NPCS §22: ACTIVE → MISSING). Исчезновение
не равно смерти: ``FOUND`` моделируется возвратом в ACTIVE, ``UNKNOWN`` и
``DEAD`` появятся позже.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    LocationKey,
    NpcId,
    WorldInstanceId,
)


class NpcStatus(StrEnum):
    ACTIVE = "ACTIVE"
    MISSING = "MISSING"


_STATUS_TRANSITIONS: dict[NpcStatus, frozenset[NpcStatus]] = {
    NpcStatus.ACTIVE: frozenset({NpcStatus.MISSING}),
    NpcStatus.MISSING: frozenset({NpcStatus.ACTIVE}),
}


@dataclass(frozen=True, slots=True)
class NpcDefinition:
    """Глобальное описание NPC (content/npcs/*.json)."""

    key: str
    name: str
    description: str
    initial_location: LocationKey
    goals: tuple[str, ...]


@dataclass(slots=True)
class Npc:
    """Конкретный NPC внутри WORLD INSTANCE."""

    id: NpcId
    world_instance_id: WorldInstanceId
    key: str
    location_key: LocationKey
    status: NpcStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: NpcId,
        world_instance_id: WorldInstanceId,
        key: str,
        location_key: LocationKey,
        now: datetime,
    ) -> "Npc":
        return cls(
            id=id,
            world_instance_id=world_instance_id,
            key=key,
            location_key=location_key,
            status=NpcStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

    def can_act(self) -> bool:
        """Исчезнувший NPC не действует в мире: его местонахождение неизвестно."""
        return self.status is NpcStatus.ACTIVE

    def ensure_can_act(self) -> None:
        if not self.can_act():
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"npc {self.id} cannot act: status={self.status}",
            )

    def apply(self, event: Event) -> None:
        """Применить событие NPC. Мир меняется только так."""
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another world instance: {event.world_instance_id}",
            )
        if event.actor != str(self.id):
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another subject: {event.actor}",
            )

        if event.type is EventType.NPC_MOVED:
            self.location_key = LocationKey(str(event.payload["to"]))
            self.updated_at = event.executed_at or event.created_at
            return

        if event.type is EventType.NPC_STATUS_CHANGED:
            self._change_status(NpcStatus(event.payload["to"]))
            self.updated_at = event.executed_at or event.created_at
            return

        raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported event type: {event.type}")

    def _change_status(self, target: NpcStatus) -> None:
        if target is self.status:
            raise DomainError(ErrorCode.INVALID_ACTION, f"npc {self.id} is already {target}")
        if target not in _STATUS_TRANSITIONS[self.status]:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"illegal npc status transition: {self.status} -> {target}",
            )
        self.status = target
