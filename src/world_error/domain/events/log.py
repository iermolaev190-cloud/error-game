"""Порт журнала событий.

Контракт:
* append-only: событие нельзя изменить или удалить;
* идемпотентность: повторный append того же ``event_id`` в том же инстансе
  поднимает ``DomainError(ALREADY_PROCESSED)`` и не меняет состояние;
* запросы всегда ограничены одним ``world_instance_id`` — данные разных
  WORLD INSTANCE не смешиваются (CODING_RULES 7).
"""

from __future__ import annotations

from typing import Protocol, Sequence

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import EventId, WorldInstanceId


class EventLog(Protocol):
    def append(self, event: Event) -> None: ...

    def has_event(self, world_instance_id: WorldInstanceId, event_id: EventId) -> bool: ...

    def get(self, world_instance_id: WorldInstanceId, event_id: EventId) -> Event:
        """Вернуть событие своего инстанса или поднять ``DomainError(NOT_FOUND)``."""
        ...

    def has_event_of_type_since(
        self,
        world_instance_id: WorldInstanceId,
        event_type: EventType,
        since_event_id: EventId,
    ) -> bool:
        """Было ли событие такого типа не раньше указанного (по порядку ``seq``).

        Нужно триггеру ``ON_EVENT_TYPE``: последствие созревает, когда мир уже
        успел породить событие нужного типа. Сравнение по ``seq``, а не по
        времени, делает проверку устойчивой к перезапуску процесса.
        """
        ...

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> Sequence[Event]: ...
