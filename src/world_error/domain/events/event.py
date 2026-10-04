"""Модель события (MASTER_SPEC §4, 19_MVP_V1_FOR_AI §12).

Событие неизменяемо: журнал событий append-only.

Типы разделены на две группы:
* инстанс-события — меняют состояние мира на уровне INSTANCE
  (``WorldInstance.apply``);
* события-действия — меняют состояние сущностей мира
  (``Character``, ``LocationState``, ``Information``), а инстанс учитывает их
  через ``WorldInstance.register_applied_event``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from world_error.domain.shared.kernel import EventId, WorldInstanceId


class EventType(StrEnum):
    """Типы событий.

    Расширяется только вместе с domain-правилом, которое это событие применяет
    (CODING_RULES 13: что меняется, какое событие, какое состояние).
    """

    # --- инстанс-события ---
    WORLD_INSTANCE_CREATED = "WORLD_INSTANCE_CREATED"
    WORLD_TICK_ADVANCED = "WORLD_TICK_ADVANCED"
    WORLD_INSTANCE_STATUS_CHANGED = "WORLD_INSTANCE_STATUS_CHANGED"

    # --- события-действия ---
    CHARACTER_CREATED = "CHARACTER_CREATED"
    CHARACTER_MOVED = "CHARACTER_MOVED"
    INFORMATION_DISCOVERED = "INFORMATION_DISCOVERED"
    KNOWLEDGE_SHARED = "KNOWLEDGE_SHARED"


@dataclass(frozen=True, slots=True)
class Event:
    """Что действительно произошло."""

    id: EventId
    world_instance_id: WorldInstanceId
    type: EventType
    created_at: datetime
    actor: str | None = None
    target: str | None = None
    cause: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    executed_at: datetime | None = None
    result: str | None = None
