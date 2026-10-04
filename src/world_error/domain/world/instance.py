"""WORLD INSTANCE и минимальный WORLD STATE.

Правило A: у созданного инстанса ``state_version == 0``; версия растёт только
событиями, применёнными к уже существующему инстансу. Поэтому событие
``WORLD_INSTANCE_CREATED`` фиксируется в журнале, но не является переходом
существующего состояния.

Учёт событий: ``state_version == world_tick == число событий, применённых после
создания``. ``WORLD_INSTANCE_STATUS_CHANGED`` — административное событие, оно
двигает только версию состояния (как в коммите 1).

Разделение осей: жизненный цикл инстанса (``InstanceLifecycle``) и среда
исполнения (``InstanceEnvironment``) — независимые вещи. ``content_version`` —
версия определений контента, а не состояние мира; её нельзя путать со
``state_version``.

Инстанс владеет только уровнем мира. Состояние персонажей, локаций и
информации меняют сами сущности — так движок не превращается в God Object.
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

# События-действия: меняют состояние сущностей мира и учитываются инстансом.
ACTION_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        EventType.CHARACTER_CREATED,
        EventType.CHARACTER_MOVED,
        EventType.INFORMATION_DISCOVERED,
        EventType.KNOWLEDGE_SHARED,
    }
)


@dataclass(slots=True)
class WorldState:
    """Минимальное состояние мира уровня инстанса.

    Хранит только первичные факты (11_WORLD_STATE_V1 §10, §36): производные
    значения не хранятся.
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
    content_version: str
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
        content_version: str,
        environment: InstanceEnvironment,
        now: datetime,
    ) -> "WorldInstance":
        """Создать инстанс. ``state_version`` созданного инстанса равен 0."""
        return cls(
            id=id,
            telegram_chat_id=telegram_chat_id,
            seed=seed,
            content_version=content_version,
            environment=environment,
            lifecycle=InstanceLifecycle.ACTIVE,
            created_at=now,
            state=WorldState(current_time=now, world_tick=0, state_version=0),
        )

    def apply(self, event: Event) -> None:
        """Применить ИНСТАНС-событие к состоянию мира.

        Единственный путь изменения состояния: значимые изменения идут через
        EVENT (CODING_RULES 5). Событие-действие сюда попасть не должно — для
        них есть ``register_applied_event``.
        """
        self._ensure_own_event(event)

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

        raise DomainError(
            ErrorCode.INVALID_ACTION,
            f"event {event.type} is an action event; use register_applied_event",
        )

    def register_applied_event(self, event: Event) -> None:
        """Учесть значимое изменение мира, вызванное событием-действием.

        Мир двигается на один тик: ``world_tick`` и ``state_version`` растут
        вместе. Само состояние сущностей меняют их собственные агрегаты.
        """
        self._ensure_own_event(event)
        if event.type not in ACTION_EVENT_TYPES:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"event {event.type} is not an action event",
            )
        self.state.world_tick += 1
        self.state.state_version += 1

    def _ensure_own_event(self, event: Event) -> None:
        if event.world_instance_id != self.id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another world instance: {event.world_instance_id}",
            )

    def _change_lifecycle(self, target: InstanceLifecycle) -> None:
        allowed = _LIFECYCLE_TRANSITIONS[self.lifecycle]
        if target not in allowed:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"illegal lifecycle transition: {self.lifecycle} -> {target}",
            )
        self.lifecycle = target
