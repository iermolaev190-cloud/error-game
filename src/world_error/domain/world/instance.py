"""WORLD INSTANCE и минимальный WORLD STATE (коммит 1 "Фундамент").

Правило A коммита 1: у созданного инстанса ``state_version == 0``; версия растёт
только событиями, применёнными к уже существующему инстансу. Поэтому событие
``WORLD_INSTANCE_CREATED`` фиксируется в журнале, но не является переходом
существующего состояния.

Правило о разделении статусов: жизненный цикл инстанса
(``InstanceLifecycle``) и среда исполнения (``InstanceEnvironment``) — две
независимые оси, они не смешиваются в одном поле.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import DomainError, ErrorCode, WorldInstanceId


class InstanceLifecycle(StrEnum):
    """Жизненный цикл WORLD INSTANCE (19_MVP_V1_FOR_AI §3)."""

    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class InstanceEnvironment(StrEnum):
    """Среда исполнения инстанса (19_MVP (design) §69)."""

    DEV = "DEV"
    TEST = "TEST"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"


_LIFECYCLE_TRANSITIONS: dict[InstanceLifecycle, frozenset[InstanceLifecycle]] = {
    InstanceLifecycle.ACTIVE: frozenset({InstanceLifecycle.PAUSED, InstanceLifecycle.ARCHIVED}),
    InstanceLifecycle.PAUSED: frozenset({InstanceLifecycle.ACTIVE, InstanceLifecycle.ARCHIVED}),
    InstanceLifecycle.ARCHIVED: frozenset(),
}


@dataclass(slots=True)
class WorldState:
    """Минимальное состояние мира уровня инстанса.

    Хранит только первичные факты (11_WORLD_STATE_V1 §10, §36): производные
    значения в коммите 1 не хранятся. Персонажи, локации, знания и экономика
    появятся в следующих коммитах.
    """

    current_time: datetime
    world_tick: int = 0
    state_version: int = 0


@dataclass(slots=True)
class WorldInstance:
    """Независимый мир. Один игровой Telegram-чат = один WORLD INSTANCE."""

    id: WorldInstanceId
    telegram_chat_id: int
    seed: int
    environment: InstanceEnvironment
    lifecycle: InstanceLifecycle
    created_at: datetime
    state: WorldState

    @classmethod
    def create(
        cls,
        *,
        id: WorldInstanceId,
        telegram_chat_id: int,
        seed: int,
        environment: InstanceEnvironment,
        now: datetime,
    ) -> "WorldInstance":
        """Создать инстанс. ``state_version`` созданного инстанса равен 0."""
        return cls(
            id=id,
            telegram_chat_id=telegram_chat_id,
            seed=seed,
            environment=environment,
            lifecycle=InstanceLifecycle.ACTIVE,
            created_at=now,
            state=WorldState(current_time=now, world_tick=0, state_version=0),
        )

    def apply(self, event: Event) -> None:
        """Применить событие к состоянию мира.

        Единственный путь изменения состояния: значимые изменения идут через
        EVENT (CODING_RULES 5). Первичные факты меняются здесь, в domain-слое.
        """
        if event.world_instance_id != self.id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another world instance: {event.world_instance_id}",
            )

        if event.type is EventType.WORLD_INSTANCE_CREATED:
            # Создание инстанса: событие фиксируется, но state_version остаётся 0.
            return

        if event.type is EventType.WORLD_TICK_ADVANCED:
            self.state.world_tick += 1
            self.state.state_version += 1
            return

        if event.type is EventType.WORLD_INSTANCE_STATUS_CHANGED:
            target = InstanceLifecycle(event.payload["to"])
            self._change_lifecycle(target)
            self.state.state_version += 1
            return

        raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported event type: {event.type}")

    def _change_lifecycle(self, target: InstanceLifecycle) -> None:
        allowed = _LIFECYCLE_TRANSITIONS[self.lifecycle]
        if target not in allowed:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"illegal lifecycle transition: {self.lifecycle} -> {target}",
            )
        self.lifecycle = target
