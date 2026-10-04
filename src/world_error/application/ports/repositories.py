"""Порты доступа к состоянию мира и журналу событий.

Все операции выполняются в контексте одного ``world_instance_id``
(MASTER_SPEC §7): ``handle_intent(world_instance_id, actor_id, intent)``.
"""

from __future__ import annotations

from typing import Callable, Protocol

from world_error.domain.events.log import EventLog
from world_error.domain.shared.kernel import WorldInstanceId
from world_error.domain.world.instance import WorldInstance


class WorldInstanceRepository(Protocol):
    def add(self, instance: WorldInstance) -> None: ...

    def get(self, world_instance_id: WorldInstanceId) -> WorldInstance:
        """Вернуть инстанс или поднять ``DomainError(NOT_FOUND)``."""
        ...

    def save(self, instance: WorldInstance) -> None: ...


class UnitOfWork(Protocol):
    """Одна транзакция на один игровой запрос.

    Состояние мира и событие фиксируются вместе: либо всё, либо ничего
    (MASTER_SPEC §14, 20_TECH_ARCHITECTURE_V1 §12).
    """

    world_instances: WorldInstanceRepository
    events: EventLog

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
