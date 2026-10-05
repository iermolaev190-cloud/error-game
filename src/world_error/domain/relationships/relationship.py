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
    STANDING = "STANDING"
    MEMBERSHIP = "MEMBERSHIP"


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


class StandingLevel(StrEnum):
    ALLIED = "ALLIED"
    COOPERATE = "COOPERATE"
    NEUTRAL = "NEUTRAL"
    COMPETITIVE = "COMPETITIVE"
    HOSTILE = "HOSTILE"
    AT_WAR = "AT_WAR"


class MembershipLevel(StrEnum):
    OUTSIDER = "OUTSIDER"
    SYMPATHISER = "SYMPATHISER"
    MEMBER = "MEMBER"
    OFFICER = "OFFICER"


class RelationshipVisibility(StrEnum):
    PUBLIC = "PUBLIC"
    SECRET = "SECRET"


class RelationshipDirection(StrEnum):
    """Шаг по лестнице вида: на ступень вверх или вниз. Без очков и чисел."""

    INCREASE = "INCREASE"
    DECREASE = "DECREASE"


RelationshipLevel = TrustLevel | SuspicionLevel | StandingLevel | MembershipLevel

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
    RelationshipKind.STANDING: (
        StandingLevel.ALLIED,
        StandingLevel.COOPERATE,
        StandingLevel.NEUTRAL,
        StandingLevel.COMPETITIVE,
        StandingLevel.HOSTILE,
        StandingLevel.AT_WAR,
    ),
    RelationshipKind.MEMBERSHIP: (
        MembershipLevel.OUTSIDER,
        MembershipLevel.SYMPATHISER,
        MembershipLevel.MEMBER,
        MembershipLevel.OFFICER,
    ),
}

_BASELINES: Mapping[RelationshipKind, RelationshipLevel] = {
    RelationshipKind.TRUST: TrustLevel.NEUTRAL,
    RelationshipKind.SUSPICION: SuspicionLevel.NONE,
    RelationshipKind.STANDING: StandingLevel.NEUTRAL,
    RelationshipKind.MEMBERSHIP: MembershipLevel.OUTSIDER,
}

SUPPORTED_SUBJECT_TYPES = (SubjectType.CHARACTER, SubjectType.NPC, SubjectType.FACTION)


@dataclass(frozen=True, slots=True)
class SubjectRef:
    """Ссылка на субъекта мира: тип + идентификатор."""

    type: SubjectType
    id: str


def ensure_supported_subject_type(subject: SubjectRef) -> None:
    """Проверить, что тип субъекта поддержан отношениями Phase 18."""
    if subject.type not in SUPPORTED_SUBJECT_TYPES:
        raise DomainError(
            ErrorCode.INVALID_ACTION,
            f"unsupported relationship subject type: {subject.type}",
        )


def ensure_relationship_kind_subjects(
    kind: RelationshipKind, holder: SubjectRef, subject: SubjectRef
) -> None:
    if kind is RelationshipKind.STANDING:
        if holder.type is not SubjectType.FACTION or subject.type is not SubjectType.FACTION:
            raise DomainError(ErrorCode.INVALID_ACTION, "STANDING requires two FACTION subjects")
    elif kind is RelationshipKind.MEMBERSHIP:
        if holder.type is not SubjectType.FACTION or subject.type is not SubjectType.CHARACTER:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                "MEMBERSHIP requires a FACTION holder and CHARACTER subject",
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
    visibility: RelationshipVisibility = RelationshipVisibility.PUBLIC

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
        visibility: RelationshipVisibility = RelationshipVisibility.PUBLIC,
    ) -> "Relationship":
        ensure_supported_subject_type(holder)
        ensure_supported_subject_type(subject)
        ensure_relationship_kind_subjects(kind, holder, subject)
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
            visibility=visibility,
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
            or str(payload.get("holder_type")) != self.holder.type.value
            or str(payload.get("subject_type")) != self.subject.type.value
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
        new_level = self.level
        if change is not None:
            if str(change.get("from")) != self.level.value:
                raise DomainError(
                    ErrorCode.INVALID_ACTION,
                    f"relationship event has stale from-level: {change.get('from')}",
                )
            new_level = coerce_level(self.kind, str(change.get("to")))
            current_index = level_index(self.kind, self.level)
            new_index = level_index(self.kind, new_level)
            distance = abs(new_index - current_index)
            if distance > 1 or (distance == 0 and "visibility" not in payload):
                raise DomainError(
                    ErrorCode.INVALID_ACTION,
                    f"illegal relationship transition: {self.level} -> {new_level}",
                )

        new_visibility = self.visibility
        if "visibility" in payload:
            try:
                new_visibility = RelationshipVisibility(str(payload["visibility"]))
            except ValueError as exc:
                raise DomainError(ErrorCode.INVALID_ACTION, "unknown relationship visibility") from exc

        if change is None and new_visibility is self.visibility:
            return
        if new_level is self.level and new_visibility is self.visibility:
            raise DomainError(ErrorCode.INVALID_ACTION, "relationship event has no effect")

        self.level = new_level
        self.visibility = new_visibility
        self.updated_at = event.executed_at or event.created_at
