"""Deterministic routing for explicit Telegram slash commands."""

from __future__ import annotations

import re

from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.routed_command import RoutedCommand
from world_error.domain.shared.kernel import CharacterId

_KEY = r"([^\W\d_][\w-]*)"
_MOVE = re.compile(rf"^/move\s+{_KEY}$", re.IGNORECASE)
_INSPECT = re.compile(rf"^/inspect\s+{_KEY}$", re.IGNORECASE)
_TAKE = re.compile(rf"^/take\s+{_KEY}$", re.IGNORECASE)
_DROP = re.compile(rf"^/drop\s+{_KEY}$", re.IGNORECASE)
_TALK = re.compile(rf"^/talk\s+{_KEY}$", re.IGNORECASE)
_GIVE = re.compile(rf"^/give\s+{_KEY}\s+{_KEY}$", re.IGNORECASE)
_SHARE = re.compile(rf"^/share\s+{_KEY}\s+{_KEY}$", re.IGNORECASE)
_TRADE = re.compile(rf"^/trade\s+{_KEY}\s+{_KEY}\s+{_KEY}$", re.IGNORECASE)

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
        if text.startswith("/"):
            text = re.sub(
                r"^(/[^@\s]+)@[A-Za-z0-9_]+(?=\s|$)",
                r"\1",
                text,
                count=1,
            )
        query_type = _QUERIES.get(text.casefold())
        if query_type is not None:
            return RoutedCommand(kind="query", query_type=query_type)

        for pattern, intent_type in (
            (_MOVE, IntentType.MOVE),
            (_INSPECT, IntentType.INSPECT),
            (_TAKE, IntentType.TAKE),
            (_DROP, IntentType.DROP),
            (_TALK, IntentType.TALK),
            (_GIVE, IntentType.GIVE),
            (_SHARE, IntentType.SHARE_KNOWLEDGE),
            (_TRADE, IntentType.TRADE),
        ):
            match = pattern.fullmatch(text)
            if match is None:
                continue
            target = match.group(1).lower()
            params = {"message": _TALK_MESSAGE} if intent_type is IntentType.TALK else {}
            if intent_type is IntentType.GIVE:
                params = {"item_key": match.group(2).lower()}
            elif intent_type is IntentType.SHARE_KNOWLEDGE:
                params = {"information_key": match.group(2).lower()}
            elif intent_type is IntentType.TRADE:
                params = {
                    "offered_item_key": match.group(2).lower(),
                    "requested_item_key": match.group(3).lower(),
                }
            return RoutedCommand(
                kind="intent",
                intent=Intent(type=intent_type, actor_id=actor_id, target=target, params=params),
            )

        return RoutedCommand(kind="none")
