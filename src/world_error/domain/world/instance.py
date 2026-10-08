"""WORLD INSTANCE и минимальный WORLD STATE.

Правило A: у созданного инстанса ``state_version == 0``; версия растёт только
событиями, применёнными к уже существующему инстансу. Поэтому событие
``WORLD_INSTANCE_CREATED`` фиксируется в журнале, но не является переходом
существующего состояния.

Учёт: ``state_version`` растёт на одно за каждое применённое state/event изменение;
``world_tick`` растёт на единицу обычного события или на агрегированную стоимость
действия. Поэтому после ``ACTION_COST_TICK_CONSUMED`` значения могут расходиться.
``WORLD_INSTANCE_STATUS_CHANGED`` — административное событие, оно двигает только
версию состояния (как в коммите 1).

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
from world_error.domain.time.world_time import WorldTime


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
        EventType.DEATH_EVENT,
        EventType.TRAVEL_STARTED,
        EventType.LEGACY_DOCUMENT_LEFT,
        EventType.LEGACY_DOCUMENT_DISCOVERED,
        EventType.CHARACTER_MOVED,
        EventType.INFORMATION_DISCOVERED,
        EventType.KNOWLEDGE_SHARED,
        EventType.NPC_MOVED,
        EventType.NPC_LEARNED,
        EventType.NPC_STATUS_CHANGED,
        EventType.FACTION_STATUS_CHANGED,
        EventType.ITEM_TAKEN,
        EventType.ITEM_DROPPED,
        EventType.ITEM_TRANSFERRED,
        EventType.EVIDENCE_LINKED,
        EventType.THEORY_CREATED,
        EventType.THEORY_EVIDENCE_LINKED,
        EventType.CONTRADICTION_MARKED,
        EventType.SUSPECT_MARKED,
        EventType.CASE_NOTE_ADDED,
        EventType.CASE_QUESTION_ADDED,
        EventType.CASE_CLOSED,
        EventType.RELATIONSHIP_CHANGED,
        EventType.CONSEQUENCE_CREATED,
        EventType.CONSEQUENCE_FAILED,
        EventType.CONSEQUENCE_CANCELLED,
        EventType.CONSEQUENCE_TRANSFORMED,
        EventType.TIME_POINT_RECORDED,
        EventType.SCHEDULED_EVENT_CREATED,
        EventType.SCHEDULED_EVENT_TRIGGERED,
        EventType.SCHEDULED_EVENT_FAILED,
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
    anchor_real_time: datetime
    time_scale: float = 1.0

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
        time_scale: float = 1.0,
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
            anchor_real_time=now,
            time_scale=time_scale,
        )

    def world_time_at(self, real_time: datetime) -> datetime:
        return WorldTime(
            self.state.current_time, self.anchor_real_time, self.time_scale
        ).at(real_time, running=self.lifecycle is InstanceLifecycle.ACTIVE)

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
            if self.lifecycle is not InstanceLifecycle.ACTIVE:
                raise DomainError(ErrorCode.INVALID_ACTION, "paused instance cannot advance time")
            now = event.executed_at or event.created_at
            self.state.current_time = self.world_time_at(now)
            self.anchor_real_time = now
            self.state.world_tick += 1
            self.state.state_version += 1
            return

        if event.type is EventType.WORLD_INSTANCE_STATUS_CHANGED:
            target = InstanceLifecycle(event.payload["to"])
            self._advance_or_freeze_time(target, event.executed_at or event.created_at)
            self._change_lifecycle(target)
            self.state.state_version += 1
            return

        raise DomainError(
            ErrorCode.INVALID_ACTION,
            f"event {event.type} is an action event; use register_applied_event",
        )

    def register_applied_event(self, event: Event) -> None:
        """Учесть значимое изменение мира, вызванное событием-действием.

        Обычное событие двигает мир на один тик и state_version. Агрегированный
        ACTION_COST_TICK_CONSUMED отдельно двигает только диапазон ticks.
        Само состояние сущностей меняют их собственные агрегаты.
        """
        self._ensure_own_event(event)
        if self.lifecycle is not InstanceLifecycle.ACTIVE:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"{self.lifecycle.value.lower()} instance cannot process action events",
            )
        if event.type not in ACTION_EVENT_TYPES:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"event {event.type} is not an action event",
            )
        self.state.world_tick += 1
        self.state.state_version += 1

    def register_action_cost(self, event: Event, *, from_tick: int, cost_ticks: int) -> None:
        self._ensure_own_event(event)
        if event.type is not EventType.ACTION_COST_TICK_CONSUMED:
            raise DomainError(ErrorCode.INVALID_ACTION, "expected ACTION_COST_TICK_CONSUMED")
        if cost_ticks < 1 or from_tick + 1 != self.state.world_tick:
            raise DomainError(ErrorCode.INVALID_ACTION, "action cost does not follow its action event")
        if (
            event.payload.get("from_tick") != from_tick
            or event.payload.get("to_tick") != from_tick + cost_ticks
            or event.payload.get("cost") != cost_ticks
        ):
            raise DomainError(ErrorCode.INVALID_ACTION, "action cost event has inconsistent tick range")
        self.state.world_tick = from_tick + cost_ticks
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

    def _advance_or_freeze_time(self, target: InstanceLifecycle, real_time: datetime) -> None:
        if self.lifecycle is InstanceLifecycle.ACTIVE and target is not InstanceLifecycle.ACTIVE:
            self.state.current_time = self.world_time_at(real_time)
            self.anchor_real_time = real_time
        elif self.lifecycle is not InstanceLifecycle.ACTIVE and target is InstanceLifecycle.ACTIVE:
            self.anchor_real_time = real_time
