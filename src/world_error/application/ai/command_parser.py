"""Small deterministic command grammar used when the AI provider is unavailable."""

from __future__ import annotations

import re

from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.interpreter import IntentContext
from world_error.domain.shared.kernel import CharacterId

_MOVE = re.compile(r"^move\s+to\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE)
_INSPECT = re.compile(r"^inspect\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE)
_TAKE = re.compile(r"^take\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE)
_DROP = re.compile(r"^drop\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE)
_TALK = re.compile(r"^talk\s+to\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE)
_GIVE = re.compile(
    r"^give\s+([a-z][a-z0-9_-]*)\s+to\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE
)
_SHARE = re.compile(
    r"^share\s+([a-z][a-z0-9_-]*)\s+with\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE
)
_TRADE = re.compile(
    r"^trade\s+([a-z][a-z0-9_-]*)\s+to\s+([a-z][a-z0-9_-]*)"
    r"\s+for\s+([a-z][a-z0-9_-]*)$",
    re.IGNORECASE,
)
_TALK_MESSAGE = "Привет. О чём поговорим?"


class CommandIntentParser:
    def interpret(self, raw_input: str, context: IntentContext) -> Intent | None:
        text = raw_input.strip()
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
            if match is not None:
                groups = tuple(group.lower() for group in match.groups())
                target = groups[0]
                params: dict[str, object] = {}
                if intent_type is IntentType.TALK:
                    params["message"] = _TALK_MESSAGE
                elif intent_type is IntentType.GIVE:
                    params = {"item_key": groups[0]}
                    target = groups[1]
                elif intent_type is IntentType.SHARE_KNOWLEDGE:
                    params = {"information_key": groups[0]}
                    target = groups[1]
                elif intent_type is IntentType.TRADE:
                    target = groups[1]
                    params = {
                        "offered_item_key": groups[0],
                        "requested_item_key": groups[2],
                    }
                return Intent(
                    type=intent_type,
                    actor_id=CharacterId(context.character_id),
                    target=target,
                    params=params,
                )
        return None
