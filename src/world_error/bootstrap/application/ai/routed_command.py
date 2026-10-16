"""Result of deterministic command routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping

from world_error.application.ai.intent import Intent


CommandKind = Literal["intent", "query", "none"]


@dataclass(frozen=True, slots=True)
class RoutedCommand:
    kind: CommandKind
    intent: Intent | None = None
    query_type: str | None = None
    query_params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in {"intent", "query", "none"}:
            raise ValueError("kind must be 'intent', 'query', or 'none'")
        if self.kind == "intent" and self.intent is None:
            raise ValueError("intent commands require an intent")
        if self.kind != "intent" and self.intent is not None:
            raise ValueError("only intent commands may contain an intent")
        if self.kind == "query" and self.query_type is None:
            raise ValueError("query commands require a query_type")
        if self.kind != "query" and self.query_type is not None:
            raise ValueError("only query commands may contain a query_type")
        object.__setattr__(self, "query_params", MappingProxyType(dict(self.query_params)))
