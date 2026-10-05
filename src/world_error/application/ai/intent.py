"""Typed player actions proposed by an interface or interpreter."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from world_error.domain.shared.kernel import CharacterId


class IntentType(StrEnum):
    MOVE = "MOVE"
    TRAVEL = "TRAVEL"
    INSPECT = "INSPECT"
    SHARE_KNOWLEDGE = "SHARE_KNOWLEDGE"
    TAKE = "TAKE"
    DROP = "DROP"
    TRADE = "TRADE"
    GIVE = "GIVE"
    LINK_EVIDENCE = "LINK_EVIDENCE"
    CREATE_THEORY = "CREATE_THEORY"
    LINK_THEORY_EVIDENCE = "LINK_THEORY_EVIDENCE"
    MARK_CONTRADICTION = "MARK_CONTRADICTION"
    MARK_SUSPECT = "MARK_SUSPECT"
    ADD_CASE_NOTE = "ADD_CASE_NOTE"
    ADD_CASE_QUESTION = "ADD_CASE_QUESTION"
    CLOSE_CASE = "CLOSE_CASE"
    INSPECT_LEGACY = "INSPECT_LEGACY"
    LEAVE_LEGACY = "LEAVE_LEGACY"
    TALK = "TALK"


@dataclass(frozen=True, slots=True)
class Intent:
    type: IntentType
    actor_id: CharacterId
    target: str | None = None
    params: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.type, IntentType):
            raise TypeError("intent type must be an IntentType")
        if not str(self.actor_id).strip():
            raise ValueError("intent actor_id must not be empty")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))
