"""Правила последствий: событие мира → шаблон последствия.

Правила приходят из контента (``content/consequences/*.json``): сам движок не
знает, на что именно реагирует конкретный мир (13_CONSEQUENCES §76–77).
В контенте ссылки идут по ключам контента (``npc_key``), потому что
идентификаторы выдаются конкретному INSTANCE — преобразование делает
application-слой при срабатывании правила.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from world_error.domain.consequences.consequence import ConsequenceTrigger
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceType,
    ConsequenceVisibility,
    ensure_not_self_triggering,
    ensure_type_matches_effect,
    validate_effect_keys,
)
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class ConsequenceRule:
    """Правило: при событии такого типа (и таком payload) создать последствие."""

    key: str
    on_event_type: EventType
    when_payload: Mapping[str, str]
    type: ConsequenceType
    scale: ConsequenceScale
    visibility: ConsequenceVisibility
    trigger: ConsequenceTrigger
    effect: ConsequenceEffect
    effect_keys: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.when_payload:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"rule {self.key} needs a non-empty when_payload",
            )
        ensure_type_matches_effect(self.type, self.effect)
        ensure_not_self_triggering(self.trigger, self.effect)
        validate_effect_keys(self.effect, self.effect_keys)

    def matches(self, event: Event) -> bool:
        if event.type is not self.on_event_type:
            return False
        return all(
            str(event.payload.get(field)) == str(value)
            for field, value in self.when_payload.items()
        )
