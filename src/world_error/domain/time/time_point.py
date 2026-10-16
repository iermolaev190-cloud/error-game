"""Временное утверждение о событии, хранимое в event metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from world_error.domain.shared.kernel import DomainError, ErrorCode, EventId


class TimePointKind(StrEnum):
    OCCURRED_AT = "OCCURRED_AT"
    DISCOVERED_AT = "DISCOVERED_AT"
    REPORTED_AT = "REPORTED_AT"
    KNOWN_AT = "KNOWN_AT"


@dataclass(frozen=True, slots=True)
class TimePoint:
    event_id: EventId
    kind: TimePointKind
    at: datetime
    subject_id: str | None = None

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            raise DomainError(ErrorCode.INVALID_ACTION, "time point must be timezone-aware")
        if self.kind is TimePointKind.KNOWN_AT and not self.subject_id:
            raise DomainError(ErrorCode.INVALID_ACTION, "KNOWN_AT requires a subject")

    def to_metadata(self) -> dict[str, str | None]:
        return {
            "event_id": str(self.event_id),
            "kind": self.kind.value,
            "at": self.at.isoformat(),
            "subject_id": self.subject_id,
        }

    @classmethod
    def from_metadata(cls, data: Mapping[str, Any]) -> "TimePoint":
        try:
            return cls(
                event_id=EventId(str(data["event_id"])),
                kind=TimePointKind(str(data["kind"])),
                at=datetime.fromisoformat(str(data["at"])),
                subject_id=None if data.get("subject_id") is None else str(data["subject_id"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError(ErrorCode.INVALID_ACTION, f"invalid time point metadata: {exc}") from exc