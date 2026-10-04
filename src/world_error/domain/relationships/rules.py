"""Правила отношений: значимые действия и недоверие к источнику.

Разделение rule vs content (20_TECH_ARCHITECTURE_V1 §23): здесь живёт правило
«значимое действие меняет отношение так», а конкретный NPC и его поступки —
в контенте и в событиях.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Mapping

from world_error.domain.relationships.relationship import (
    RelationshipDirection,
    RelationshipKind,
    SuspicionLevel,
    TrustLevel,
)


class SignificantAction(StrEnum):
    """Значимые действия, которые NPC помнит (05_NPCS §13, §29)."""

    HELPED = "HELPED"
    BETRAYED = "BETRAYED"
    LIED_TO = "LIED_TO"


_EFFECTS: Mapping[
    SignificantAction, tuple[tuple[RelationshipKind, RelationshipDirection], ...]
] = {
    SignificantAction.HELPED: ((RelationshipKind.TRUST, RelationshipDirection.INCREASE),),
    SignificantAction.BETRAYED: (
        (RelationshipKind.TRUST, RelationshipDirection.DECREASE),
        (RelationshipKind.SUSPICION, RelationshipDirection.INCREASE),
    ),
    SignificantAction.LIED_TO: (
        (RelationshipKind.TRUST, RelationshipDirection.DECREASE),
        (RelationshipKind.SUSPICION, RelationshipDirection.INCREASE),
    ),
}

# Недоверие к источнику знания: только крайние ступени, не «любое недоверие».
_DISTRUSTED_TRUST_LEVELS = frozenset({TrustLevel.HOSTILE})
_DISTRUSTED_SUSPICION_LEVELS = frozenset({SuspicionLevel.HIGH})


def effects_of(
    action: SignificantAction,
) -> tuple[tuple[RelationshipKind, RelationshipDirection], ...]:
    return _EFFECTS[action]


def is_source_distrusted(
    *,
    trust_level: TrustLevel | None,
    suspicion_level: SuspicionLevel | None,
) -> bool:
    """Считается ли источник знания недоверенным для держателя отношения.

    ``None`` означает отсутствие записи, то есть базовую ступень: NEUTRAL и
    NONE не считаются недоверием.
    """
    if trust_level is not None and trust_level in _DISTRUSTED_TRUST_LEVELS:
        return True
    if suspicion_level is not None and suspicion_level in _DISTRUSTED_SUSPICION_LEVELS:
        return True
    return False
