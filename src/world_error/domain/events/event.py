"""Модель события (MASTER_SPEC §4, 19_MVP_V1_FOR_AI §12).

Событие неизменяемо: журнал событий append-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from world_error.domain.shared.kernel import EventId, WorldInstanceId


class EventType(StrEnum):
    """Типы событий коммита 1.

    Расширяется только вместе с domain-правилом, которое это событие применяет
    (CODING_RULES 13: что меняется, какое событие, какое состояние).
    """

    WORLD_INSTANCE_CREATED = "WORLD_INSTANCE_CREATED"
    WORLD_TICK_ADVANCED = "WORLD_TICK_ADVANCED"
    WORLD_INSTANCE_STATUS_CHANGED = "WORLD_INSTANCE_STATUS_CHANGED"


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
