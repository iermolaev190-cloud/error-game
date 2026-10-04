"""Ленивое вычисление WORLD_TIME от сохранённого real-time anchor."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from world_error.domain.shared.kernel import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class WorldTime:
    anchor_world_time: datetime
    anchor_real_time: datetime
    time_scale: float = 1.0

    def __post_init__(self) -> None:
        if self.anchor_world_time.tzinfo is None or self.anchor_real_time.tzinfo is None:
            raise DomainError(ErrorCode.INVALID_ACTION, "world time anchors must be timezone-aware")
        if not math.isfinite(self.time_scale) or self.time_scale < 0:
            raise DomainError(ErrorCode.INVALID_ACTION, "time_scale must be finite and non-negative")

    def at(self, real_time: datetime, *, running: bool = True) -> datetime:
        if real_time.tzinfo is None:
            raise DomainError(ErrorCode.INVALID_ACTION, "real time must be timezone-aware")
        if not running or real_time <= self.anchor_real_time:
            return self.anchor_world_time
        elapsed = real_time - self.anchor_real_time
        return self.anchor_world_time + timedelta(seconds=elapsed.total_seconds() * self.time_scale)

    def reanchor(self, real_time: datetime, *, running: bool = True) -> "WorldTime":
        current = self.at(real_time, running=running)
        return WorldTime(
            anchor_world_time=current,
            anchor_real_time=real_time,
            time_scale=self.time_scale,
        )

    def pause(self, real_time: datetime) -> "WorldTime":
        return self.reanchor(real_time)

    def resume(self, real_time: datetime) -> "WorldTime":
        return WorldTime(
            anchor_world_time=self.anchor_world_time,
            anchor_real_time=real_time,
            time_scale=self.time_scale,
        )