"""Positive, explicit world-tick cost for an action."""

from __future__ import annotations

from dataclasses import dataclass

from world_error.domain.shared.kernel import DomainError, ErrorCode


@dataclass(frozen=True, slots=True)
class CostTicks:
    value: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, int)
            or self.value < 1
        ):
            raise DomainError(ErrorCode.INVALID_ACTION, "CostTicks must be a positive integer")

    def __int__(self) -> int:
        return self.value
