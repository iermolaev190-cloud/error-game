"""Словарь последствий: типы, масштабы, видимость, эффекты.

13_CONSEQUENCES: §5 (типы), §29 (видимость), §36–§41 (масштаб), §91 (цикл).
Ключевое разделение: **тип** описывает, какой области мира коснулось последствие,
**эффект** — что именно механически меняется. В коммите 6 реализованы только те
типы, для которых существуют подсистемы (знание, отношения, NPC и локации).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping

from world_error.domain.events.event import EventType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.npcs.npc import NpcStatus
from world_error.domain.relationships.relationship import (
    RelationshipDirection,
    RelationshipKind,
    SubjectRef,
    ensure_supported_subject_type,
)
from world_error.domain.shared.kernel import DomainError, ErrorCode


class ConsequenceType(StrEnum):
    """Минимальный набор из §5: только те типы, у которых есть подсистема."""

    INFORMATIONAL = "INFORMATIONAL"
    RELATIONAL = "RELATIONAL"
    PHYSICAL = "PHYSICAL"


class ConsequenceScale(StrEnum):
    """§36–§41. CANONICAL — уровень автора, в движок не входит."""

    PERSONAL = "PERSONAL"
    LOCAL = "LOCAL"
    REGIONAL = "REGIONAL"
    GLOBAL = "GLOBAL"


class ConsequenceVisibility(StrEnum):
    """§29. В коммите 6 видимость — классификация: она не ветвит поведение.

    Скрытость последствий обеспечивается структурно: ни один публичный запрос
    (проекция локации, show-*) последствий не показывает вообще.
    """

    VISIBLE = "VISIBLE"
    PARTIALLY_VISIBLE = "PARTIALLY_VISIBLE"
    HIDDEN = "HIDDEN"
    INDIRECT = "INDIRECT"
    UNKNOWN = "UNKNOWN"


class ConsequenceStatus(StrEnum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TRANSFORMED = "TRANSFORMED"


class TriggerKind(StrEnum):
    IMMEDIATE = "IMMEDIATE"
    AFTER_TICKS = "AFTER_TICKS"
    ON_EVENT_TYPE = "ON_EVENT_TYPE"


class CauseOrigin(StrEnum):
    """Кто породил причину (§79): субъект, сам мир или другое последствие."""

    ACTOR = "ACTOR"
    WORLD = "WORLD"
    CONSEQUENCE = "CONSEQUENCE"


class ConsequenceEffect(StrEnum):
    """Механизмы, которыми последствие меняет мир.

    Каждый эффект порождает **существующее** событие мира, поэтому последствия
    не открывают второй путь изменения состояния.
    """

    INFORMATIONAL_LEARN = "INFORMATIONAL_LEARN"
    RELATIONAL_SHIFT = "RELATIONAL_SHIFT"
    PHYSICAL_STATUS_CHANGE = "PHYSICAL_STATUS_CHANGE"
    PHYSICAL_RELOCATE = "PHYSICAL_RELOCATE"


EFFECT_EVENT_TYPES: Mapping[ConsequenceEffect, EventType] = {
    ConsequenceEffect.INFORMATIONAL_LEARN: EventType.NPC_LEARNED,
    ConsequenceEffect.RELATIONAL_SHIFT: EventType.RELATIONSHIP_CHANGED,
    ConsequenceEffect.PHYSICAL_STATUS_CHANGE: EventType.NPC_STATUS_CHANGED,
    ConsequenceEffect.PHYSICAL_RELOCATE: EventType.NPC_MOVED,
}

EFFECT_TYPES: Mapping[ConsequenceEffect, ConsequenceType] = {
    ConsequenceEffect.INFORMATIONAL_LEARN: ConsequenceType.INFORMATIONAL,
    ConsequenceEffect.RELATIONAL_SHIFT: ConsequenceType.RELATIONAL,
    ConsequenceEffect.PHYSICAL_STATUS_CHANGE: ConsequenceType.PHYSICAL,
    ConsequenceEffect.PHYSICAL_RELOCATE: ConsequenceType.PHYSICAL,
}

# Обязательные поля payload в сохранённом виде: только идентификаторы, потому что
# последствие должно оставаться детерминированным даже если контент изменится.
PAYLOAD_FIELDS: Mapping[ConsequenceEffect, tuple[str, ...]] = {
    ConsequenceEffect.INFORMATIONAL_LEARN: ("npc_id", "information_key"),
    ConsequenceEffect.RELATIONAL_SHIFT: (
        "holder_type",
        "holder_id",
        "subject_type",
        "subject_id",
        "kind",
        "direction",
    ),
    ConsequenceEffect.PHYSICAL_STATUS_CHANGE: ("npc_id", "status"),
    ConsequenceEffect.PHYSICAL_RELOCATE: ("npc_id", "to_location_key"),
}

# Обязательные поля в контенте правил: там ссылки идут по ключам контента,
# потому что идентификаторы выдаются конкретному INSTANCE.
KEY_FIELDS: Mapping[ConsequenceEffect, tuple[str, ...]] = {
    ConsequenceEffect.INFORMATIONAL_LEARN: ("npc_key", "information_key"),
    ConsequenceEffect.RELATIONAL_SHIFT: (
        "holder_type",
        "holder_key",
        "subject_type",
        "subject_key",
        "kind",
        "direction",
    ),
    ConsequenceEffect.PHYSICAL_STATUS_CHANGE: ("npc_key", "status"),
    ConsequenceEffect.PHYSICAL_RELOCATE: ("npc_key", "to_location_key"),
}


def event_type_for(effect: ConsequenceEffect) -> EventType:
    return EFFECT_EVENT_TYPES[effect]


def effect_type_of(effect: ConsequenceEffect) -> ConsequenceType:
    return EFFECT_TYPES[effect]


def _parse(enum_type, value: Any, field: str):  # noqa: ANN001, ANN202
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise DomainError(
            ErrorCode.INVALID_ACTION, f"unknown {field}: {value!r}"
        ) from exc


def ensure_type_matches_effect(
    consequence_type: ConsequenceType, effect: ConsequenceEffect
) -> None:
    expected = EFFECT_TYPES[effect]
    if consequence_type is not expected:
        raise DomainError(
            ErrorCode.INVALID_ACTION,
            f"effect {effect.value} belongs to type {expected.value}, not {consequence_type.value}",
        )


def is_self_triggering(trigger, effect: ConsequenceEffect) -> bool:  # noqa: ANN001
    """Последствие не может запускаться событием, которое само же и порождает."""
    return (
        trigger.kind is TriggerKind.ON_EVENT_TYPE
        and trigger.event_type is event_type_for(effect)
    )


def ensure_not_self_triggering(trigger, effect: ConsequenceEffect) -> None:  # noqa: ANN001
    if is_self_triggering(trigger, effect):
        raise DomainError(
            ErrorCode.INVALID_ACTION,
            f"consequence cannot be triggered by {event_type_for(effect).value}: "
            "it produces that event itself",
        )


def validate_effect_payload(effect: ConsequenceEffect, payload: Mapping[str, Any]) -> None:
    """Проверить, что payload эффекта полон и его значения допустимы."""
    missing = [
        field
        for field in PAYLOAD_FIELDS[effect]
        if payload.get(field) is None or str(payload.get(field)) == ""
    ]
    if missing:
        raise DomainError(
            ErrorCode.INVALID_ACTION,
            f"effect {effect.value} requires: {', '.join(missing)}",
        )

    if effect is ConsequenceEffect.RELATIONAL_SHIFT:
        holder = SubjectRef(
            type=_parse(SubjectType, payload["holder_type"], "holder_type"),
            id=str(payload["holder_id"]),
        )
        subject = SubjectRef(
            type=_parse(SubjectType, payload["subject_type"], "subject_type"),
            id=str(payload["subject_id"]),
        )
        ensure_supported_subject_type(holder)
        ensure_supported_subject_type(subject)
        if SubjectType.FACTION in (holder.type, subject.type):
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                "faction relationships cannot be changed by consequences",
            )
        _parse(RelationshipKind, payload["kind"], "relationship kind")
        _parse(RelationshipDirection, payload["direction"], "relationship direction")
        return

    if effect is ConsequenceEffect.PHYSICAL_STATUS_CHANGE:
        _parse(NpcStatus, payload["status"], "npc status")


def validate_effect_keys(effect: ConsequenceEffect, keys: Mapping[str, Any]) -> None:
    """Проверить шаблон правила: он ссылается на контент по ключам."""
    missing = [
        field for field in KEY_FIELDS[effect] if keys.get(field) is None or str(keys.get(field)) == ""
    ]
    if missing:
        raise DomainError(
            ErrorCode.INVALID_ACTION,
            f"effect {effect.value} rule requires: {', '.join(missing)}",
        )
    if effect is ConsequenceEffect.RELATIONAL_SHIFT:
        holder_type = _parse(SubjectType, keys["holder_type"], "holder_type")
        subject_type = _parse(SubjectType, keys["subject_type"], "subject_type")
        ensure_supported_subject_type(SubjectRef(type=holder_type, id=str(keys.get("holder_key", ""))))
        ensure_supported_subject_type(
            SubjectRef(type=subject_type, id=str(keys.get("subject_key", "")))
        )
        if SubjectType.FACTION in (holder_type, subject_type):
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                "faction relationships cannot be changed by consequences",
            )
        _parse(RelationshipKind, keys["kind"], "relationship kind")
        _parse(RelationshipDirection, keys["direction"], "relationship direction")
        return

    if effect is ConsequenceEffect.PHYSICAL_STATUS_CHANGE:
        _parse(NpcStatus, keys["status"], "npc status")
