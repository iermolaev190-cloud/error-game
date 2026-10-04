"""Отношения между субъектами мира (05_NPCS §10–§13, §29).

Три принципа, заложенные в модель:

1. **Отношение — не одно число.** У пары (holder, subject) столько записей,
   сколько видов отношений реально менялось; каждый вид живёт на своей
   именованной лестнице. 11_WORLD_STATE_V1 §7 предупреждает против превращения
   мира в набор числовых параметров, поэтому ступени именованные, а числа
   наружу не выходят вообще.
2. **Асимметрия структурная.** ``holder → subject`` и ``subject → holder`` —
   разные строки с разными ключами. Установка A → B не меняет B → A.
3. **Изменение — только через событие.** ``apply`` принимает
   ``RELATIONSHIP_CHANGED``, проверяет пару и делает ровно один шаг по лестнице.

holder — субъект, чья это оценка; subject — тот, о ком она. Оба должны
принадлежать одному WORLD INSTANCE; FACTION отклоняется до Phase 18.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from world_error.domain.events.event import Event, EventType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    RelationshipId,
    WorldInstanceId,
)


class RelationshipKind(StrEnum):
    """Минимальный набор видов для MVP. Остальные — позже."""

    TRUST = "TRUST"
    SUSPICION = "SUSPICION"


class TrustLevel(StrEnum):
    HOSTILE = "HOSTILE"
    WARY = "WARY"
    NEUTRAL = "NEUTRAL"
    FRIENDLY = "FRIENDLY"
    DEVOTED = "DEVOTED"


class SuspicionLevel(StrEnum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RelationshipDirection(StrEnum):
    """Шаг по лестнице вида: на ступень вверх или вниз. Без очков и чисел."""

    INCREASE = "INCREASE"
    DECREASE = "DECREASE"


RelationshipLevel = TrustLevel | SuspicionLevel

_LADDERS: Mapping[RelationshipKind, tuple[RelationshipLevel, ...]] = {
    RelationshipKind.TRUST: (
        TrustLevel.HOSTILE,
        TrustLevel.WARY,
        TrustLevel.NEUTRAL,
        TrustLevel.FRIENDLY,
        TrustLevel.DEVOTED,
    ),
    RelationshipKind.SUSPICION: (
        SuspicionLevel.NONE,
        SuspicionLevel.LOW,
        SuspicionLevel.MEDIUM,
        SuspicionLevel.HIGH,
    ),
}

_BASELINES: Mapping[RelationshipKind, RelationshipLevel] = {
    RelationshipKind.TRUST: TrustLevel.NEUTRAL,
    RelationshipKind.SUSPICION: SuspicionLevel.NONE,
}

SUPPORTED_SUBJECT_TYPES = (SubjectType.CHARACTER, SubjectType.NPC)


@dataclass(frozen=True, slots=True)
class SubjectRef:
    """Ссылка на субъекта мира: тип + идентификатор."""

    type: SubjectType
    id: str


def ensure_supported_subject_type(subject: SubjectRef) -> None:
    """FACTION в отношениях появится вместе с фракциями (Phase 18)."""
    if subject.type not in SUPPORTED_SUBJECT_TYPES:
        raise DomainError(
            ErrorCode.INVALID_ACTION,
            f"unsupported relationship subject type: {subject.type}",
        )


def baseline_level(kind: RelationshipKind) -> RelationshipLevel:
    """Ступень, которая действует, пока записи об отношении нет."""
    return _BASELINES[kind]


def level_index(kind: RelationshipKind, level: RelationshipLevel | str) -> int:
    ladder = _LADDERS[kind]
    for index, candidate in enumerate(ladder):
        if candidate.value == str(level):
            return index
    raise DomainError(
        ErrorCode.INVALID_ACTION,
        f"unknown {kind} level: {level}",
    )


def coerce_level(kind: RelationshipKind, level: RelationshipLevel | str) -> RelationshipLevel:
    return _LADDERS[kind][level_index(kind, level)]


def step_level(
    kind: RelationshipKind,
    level: RelationshipLevel | str,
    direction: RelationshipDirection,
) -> RelationshipLevel | None:
    """Одна ступень вверх/вниз. ``None`` — уже край лестницы, менять нечего."""
    ladder = _LADDERS[kind]
    index = level_index(kind, level)
    target = index + 1 if direction is RelationshipDirection.INCREASE else index - 1
    if target < 0 or target >= len(ladder):
        return None
    return ladder[target]


@dataclass(slots=True)
class Relationship:
    """Отношение holder → subject одного вида."""

    id: RelationshipId
    world_instance_id: WorldInstanceId
    holder: SubjectRef
    subject: SubjectRef
    kind: RelationshipKind
    level: RelationshipLevel
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: RelationshipId,
        holder: SubjectRef,
        holder_instance_id: WorldInstanceId,
        subject: SubjectRef,
        subject_instance_id: WorldInstanceId,
        kind: RelationshipKind,
        now: datetime,
        level: RelationshipLevel | None = None,
    ) -> "Relationship":
        ensure_supported_subject_type(holder)
        ensure_supported_subject_type(subject)
        if holder_instance_id != subject_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                "relationship subjects belong to different world instances",
            )
        if holder == subject:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                "a subject cannot have a relationship with itself",
            )
        return cls(
            id=id,
            world_instance_id=holder_instance_id,
            holder=holder,
            subject=subject,
            kind=kind,
            level=coerce_level(kind, level if level is not None else baseline_level(kind)),
            created_at=now,
            updated_at=now,
        )

    def apply(self, event: Event) -> None:
        """Применить событие изменения отношения: ровно один шаг по лестнице."""
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"event {event.id} belongs to another world instance: {event.world_instance_id}",
            )
        if event.type is not EventType.RELATIONSHIP_CHANGED:
            raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported event type: {event.type}")

        payload = event.payload
        if (
            str(payload.get("holder_id")) != self.holder.id
            or str(payload.get("subject_id")) != self.subject.id
        ):
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                "event changes another relationship pair",
            )

        change = next(
            (
                item
                for item in payload.get("changes", ())
                if str(item.get("kind")) == self.kind.value
            ),
            None,
        )
        if change is None:
            return  # этот вид отношения в событии не менялся

        new_level = coerce_level(self.kind, str(change.get("to")))
        current_index = level_index(self.kind, self.level)
        new_index = level_index(self.kind, new_level)
        if abs(new_index - current_index) != 1:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"illegal relationship step: {self.level} -> {new_level}",
            )
        self.level = new_level
        self.updated_at = event.executed_at or event.created_at
