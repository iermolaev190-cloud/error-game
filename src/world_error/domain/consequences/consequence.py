"""Сущность последствия и его триггеры (13_CONSEQUENCES).

Последствие — не наказание и не награда, а изменение мира: у него **всегда**
есть причина-событие (§14 канона), оно может быть отложенным, скрытым и
ветвящимся, и применяется тем же путём, что и прямые действия — через EVENT.

Модуль не знает про БД и репозитории: он описывает, *когда* последствие
созревает, а решение об этом принимает application-слой.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, Sequence

from world_error.domain.consequences.vocabulary import (
    CauseOrigin,
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceStatus,
    ConsequenceType,
    ConsequenceVisibility,
    TriggerKind,
    ensure_not_self_triggering,
    ensure_type_matches_effect,
    validate_effect_payload,
)
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    ConsequenceId,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
)

# Эффект-события последствий помечаются этим префиксом в ``cause``: по нему
# вычисляется происхождение (§79) и собирается граф последствий.
CONSEQUENCE_EVENT_PREFIX = "consequence:"

# Синтетический «актор» движка (коммит 1): это не субъект мира, поэтому событие
# с таким actor считается порождённым миром, а не действующим лицом.
SYSTEM_ACTOR = "system"


def consequence_cause_of(consequence_id: ConsequenceId) -> str:
    return f"{CONSEQUENCE_EVENT_PREFIX}{consequence_id}"


@dataclass(frozen=True, slots=True)
class ConsequenceCause:
    """Одна причина последствия. У последствия их может быть несколько (§26)."""

    event_id: EventId
    origin: CauseOrigin


def origin_of(event: Event) -> CauseOrigin:
    """Кто/что породило причину: субъект, мир или другое последствие."""
    if (event.cause or "").startswith(CONSEQUENCE_EVENT_PREFIX):
        return CauseOrigin.CONSEQUENCE
    if event.actor and event.actor != SYSTEM_ACTOR:
        return CauseOrigin.ACTOR
    return CauseOrigin.WORLD


@dataclass(frozen=True, slots=True)
class ConsequenceTrigger:
    """Когда последствие созревает."""

    kind: TriggerKind
    delay_ticks: int | None = None
    event_type: EventType | None = None

    def __post_init__(self) -> None:
        if self.kind is TriggerKind.IMMEDIATE and (
            self.delay_ticks is not None or self.event_type is not None
        ):
            raise DomainError(
                ErrorCode.INVALID_ACTION, "IMMEDIATE trigger takes no parameters"
            )
        if self.kind is TriggerKind.AFTER_TICKS and (
            self.delay_ticks is None or self.delay_ticks <= 0
        ):
            raise DomainError(
                ErrorCode.INVALID_ACTION, "AFTER_TICKS requires delay_ticks > 0"
            )
        if self.kind is TriggerKind.ON_EVENT_TYPE and self.event_type is None:
            raise DomainError(
                ErrorCode.INVALID_ACTION, "ON_EVENT_TYPE requires event_type"
            )

    @classmethod
    def immediate(cls) -> "ConsequenceTrigger":
        return cls(kind=TriggerKind.IMMEDIATE)

    @classmethod
    def after_ticks(cls, ticks: int) -> "ConsequenceTrigger":
        return cls(kind=TriggerKind.AFTER_TICKS, delay_ticks=int(ticks))

    @classmethod
    def on_event_type(cls, event_type: EventType | str) -> "ConsequenceTrigger":
        return cls(kind=TriggerKind.ON_EVENT_TYPE, event_type=EventType(str(event_type)))

    @property
    def waits_for_event(self) -> bool:
        return self.kind is TriggerKind.ON_EVENT_TYPE

    def due_tick(self, *, created_tick: int) -> int:
        """Тик, раньше которого последствие созреть не может."""
        if self.kind is TriggerKind.AFTER_TICKS:
            return created_tick + int(self.delay_ticks)
        return created_tick

    def tick_is_due(self, *, current_tick: int, due_tick: int) -> bool:
        """Созрело ли по времени. Для ON_EVENT_TYPE решает не тик, а событие."""
        if self.kind is TriggerKind.IMMEDIATE:
            return True
        if self.kind is TriggerKind.AFTER_TICKS:
            return current_tick >= due_tick
        return False

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind.value}
        if self.delay_ticks is not None:
            payload["delay_ticks"] = self.delay_ticks
        if self.event_type is not None:
            payload["event_type"] = self.event_type.value
        return payload


@dataclass(slots=True)
class Consequence:
    """Запланированное изменение мира, всегда с причиной."""

    id: ConsequenceId
    world_instance_id: WorldInstanceId
    causes: tuple[ConsequenceCause, ...]
    type: ConsequenceType
    scale: ConsequenceScale
    visibility: ConsequenceVisibility
    trigger: ConsequenceTrigger
    effect: ConsequenceEffect
    payload: Mapping[str, Any]
    due_tick: int
    created_at: datetime
    status: ConsequenceStatus = ConsequenceStatus.PENDING
    rule_key: str | None = None
    applied_at: datetime | None = None
    applied_event_id: EventId | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def source_event_id(self) -> EventId:
        """Первопричина: последствие без причины существовать не может."""
        return self.causes[0].event_id

    @classmethod
    def create(
        cls,
        *,
        id: ConsequenceId,
        world_instance_id: WorldInstanceId,
        causes: Sequence[ConsequenceCause],
        type: ConsequenceType,
        scale: ConsequenceScale,
        visibility: ConsequenceVisibility,
        trigger: ConsequenceTrigger,
        effect: ConsequenceEffect,
        payload: Mapping[str, Any],
        created_tick: int,
        now: datetime,
        rule_key: str | None = None,
    ) -> "Consequence":
        if not causes:
            raise DomainError(
                ErrorCode.INVALID_ACTION, "consequence must have at least one cause"
            )
        event_ids = [cause.event_id for cause in causes]
        if len(set(event_ids)) != len(event_ids):
            raise DomainError(
                ErrorCode.INVALID_ACTION, "consequence causes must be unique"
            )
        ensure_type_matches_effect(type, effect)
        ensure_not_self_triggering(trigger, effect)
        validate_effect_payload(effect, payload)
        return cls(
            id=id,
            world_instance_id=world_instance_id,
            causes=tuple(causes),
            type=type,
            scale=scale,
            visibility=visibility,
            trigger=trigger,
            effect=effect,
            payload=dict(payload),
            due_tick=trigger.due_tick(created_tick=created_tick),
            created_at=now,
            rule_key=rule_key,
        )

    def can_apply(self) -> bool:
        return self.status is ConsequenceStatus.PENDING

    def ensure_can_apply(self) -> None:
        if not self.can_apply():
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"consequence {self.id} is already {self.status.value}",
            )

    def mark_applied(self, *, event_id: EventId, now: datetime) -> bool:
        """Перевести в APPLIED. Повторный вызов — no-op (идемпотентность)."""
        if not self.can_apply():
            return False
        if not event_id:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                "applied consequence requires an event",
            )
        self.status = ConsequenceStatus.APPLIED
        self.applied_at = now
        self.applied_event_id = event_id
        return True

    def mark_failed(self, *, now: datetime) -> bool:
        """Перевести в FAILED: эффект оказался невозможен. Каскад продолжается."""
        if not self.can_apply():
            return False
        self.status = ConsequenceStatus.FAILED
        self.applied_at = now
        return True

    def cancel(self, *, now: datetime) -> bool:
        if self.status is ConsequenceStatus.CANCELLED:
            return False
        if self.status is not ConsequenceStatus.PENDING:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"only PENDING consequences can be cancelled (got {self.status.value})",
            )
        self.status = ConsequenceStatus.CANCELLED
        self.applied_at = now
        return True

    def mark_transformed(self, *, now: datetime) -> bool:
        if self.status is ConsequenceStatus.TRANSFORMED:
            return False
        if self.status is not ConsequenceStatus.PENDING:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"only PENDING consequences can be transformed (got {self.status.value})",
            )
        self.status = ConsequenceStatus.TRANSFORMED
        self.applied_at = now
        return True

    def has_cause(self, event_id: EventId) -> bool:
        return any(cause.event_id == event_id for cause in self.causes)
