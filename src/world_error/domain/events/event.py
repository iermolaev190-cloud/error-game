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

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from world_error.domain.shared.kernel import EventId, WorldInstanceId
from world_error.domain.time.time_point import TimePoint


class EventType(StrEnum):
    """Типы событий.

    Расширяется только вместе с domain-правилом, которое это событие применяет
    (CODING_RULES 13: что меняется, какое событие, какое состояние).
    """

    # --- инстанс-события ---
    WORLD_INSTANCE_CREATED = "WORLD_INSTANCE_CREATED"
    WORLD_TICK_ADVANCED = "WORLD_TICK_ADVANCED"
    WORLD_INSTANCE_STATUS_CHANGED = "WORLD_INSTANCE_STATUS_CHANGED"
    TIME_POINT_RECORDED = "TIME_POINT_RECORDED"
    SCHEDULED_EVENT_CREATED = "SCHEDULED_EVENT_CREATED"
    SCHEDULED_EVENT_TRIGGERED = "SCHEDULED_EVENT_TRIGGERED"

    # --- события-действия ---
    CHARACTER_CREATED = "CHARACTER_CREATED"
    DEATH_EVENT = "DEATH_EVENT"
    TRAVEL_STARTED = "TRAVEL_STARTED"
    ACTION_COST_TICK_CONSUMED = "ACTION_COST_TICK_CONSUMED"
    CHARACTER_MOVED = "CHARACTER_MOVED"
    INFORMATION_DISCOVERED = "INFORMATION_DISCOVERED"
    KNOWLEDGE_SHARED = "KNOWLEDGE_SHARED"
    NPC_MOVED = "NPC_MOVED"
    NPC_LEARNED = "NPC_LEARNED"
    NPC_STATUS_CHANGED = "NPC_STATUS_CHANGED"
    FACTION_STATUS_CHANGED = "FACTION_STATUS_CHANGED"
    ITEM_TAKEN = "ITEM_TAKEN"
    ITEM_DROPPED = "ITEM_DROPPED"
    ITEM_TRANSFERRED = "ITEM_TRANSFERRED"
    RELATIONSHIP_CHANGED = "RELATIONSHIP_CHANGED"
    CONSEQUENCE_CREATED = "CONSEQUENCE_CREATED"
    CONSEQUENCE_FAILED = "CONSEQUENCE_FAILED"
    CONSEQUENCE_CANCELLED = "CONSEQUENCE_CANCELLED"
    CONSEQUENCE_TRANSFORMED = "CONSEQUENCE_TRANSFORMED"
    LEGACY_DOCUMENT_LEFT = "LEGACY_DOCUMENT_LEFT"
    LEGACY_DOCUMENT_DISCOVERED = "LEGACY_DOCUMENT_DISCOVERED"
    SCHEDULED_EVENT_FAILED = "SCHEDULED_EVENT_FAILED"


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
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def time_points(self) -> tuple[TimePoint, ...]:
      values = self.metadata.get("time_points", ())
      return tuple(TimePoint.from_metadata(value) for value in values)

    def with_time_point(self, time_point: TimePoint) -> "Event":
      metadata = dict(self.metadata)
      values = list(metadata.get("time_points", ()))
      values.append(time_point.to_metadata())
      metadata["time_points"] = values
      return replace(self, metadata=metadata)
