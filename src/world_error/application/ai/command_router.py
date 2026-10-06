"""Deterministic routing for explicit Telegram slash commands."""

from __future__ import annotations

import re

from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.routed_command import RoutedCommand
from world_error.domain.shared.kernel import CharacterId

_KEY = r"([a-z][a-z0-9_-]*)"
_MOVE = re.compile(rf"^/move\s+{_KEY}$", re.IGNORECASE)
_INSPECT = re.compile(rf"^/inspect\s+{_KEY}$", re.IGNORECASE)
_TAKE = re.compile(rf"^/take\s+{_KEY}$", re.IGNORECASE)
_DROP = re.compile(rf"^/drop\s+{_KEY}$", re.IGNORECASE)
_TALK = re.compile(rf"^/talk\s+{_KEY}$", re.IGNORECASE)

_QUERIES = {
    "/look": "look",
    "/npcs": "npcs",
    "/inventory": "inventory",
    "/knowledge": "knowledge",
    "/character": "character",
    "/help": "help",
}
_TALK_MESSAGE = "Привет. О чём поговорим?"


class CommandRouter:
    """Parse explicit commands without accessing or mutating world state."""

    def route(self, raw_text: str, *, actor_id: CharacterId) -> RoutedCommand:
        text = raw_text.strip()
        query_type = _QUERIES.get(text.casefold())
        if query_type is not None:
            return RoutedCommand(kind="query", query_type=query_type)

        for pattern, intent_type in (
            (_MOVE, IntentType.MOVE),
            (_INSPECT, IntentType.INSPECT),
            (_TAKE, IntentType.TAKE),
            (_DROP, IntentType.DROP),
            (_TALK, IntentType.TALK),
        ):
            match = pattern.fullmatch(text)
            if match is None:
                continue
            target = match.group(1).lower()
            params = {"message": _TALK_MESSAGE} if intent_type is IntentType.TALK else {}
            return RoutedCommand(
                kind="intent",
                intent=Intent(type=intent_type, actor_id=actor_id, target=target, params=params),
            )

        return RoutedCommand(kind="none")
