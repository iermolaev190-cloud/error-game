"""A posthumous document left in a location, not an inventory item."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from world_error.domain.shared.kernel import (
    CharacterId,
    EventId,
    LegacyDocumentId,
    LocationKey,
    WorldInstanceId,
)


@dataclass(frozen=True, slots=True)
class LegacyDocument:
    id: LegacyDocumentId
    world_instance_id: WorldInstanceId
    document_key: str
    location_key: LocationKey
    created_by_character_id: CharacterId
    death_event_id: EventId
    created_event_id: EventId
    content: str
    created_at: datetime
