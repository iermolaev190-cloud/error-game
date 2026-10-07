"""Small deterministic command grammar used when the AI provider is unavailable."""

from __future__ import annotations

import re

from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.interpreter import IntentContext
from world_error.domain.shared.kernel import CharacterId

_KEY = r"([^\W\d_][\w-]*)"
_MOVE = re.compile(rf"^move\s+to\s+{_KEY}$", re.IGNORECASE)
_INSPECT = re.compile(rf"^inspect\s+{_KEY}$", re.IGNORECASE)
_TAKE = re.compile(rf"^take\s+{_KEY}$", re.IGNORECASE)
_DROP = re.compile(rf"^drop\s+{_KEY}$", re.IGNORECASE)
_TALK = re.compile(rf"^talk\s+to\s+{_KEY}$", re.IGNORECASE)
_GIVE = re.compile(
    rf"^give\s+{_KEY}\s+to\s+{_KEY}$", re.IGNORECASE
)
_SHARE = re.compile(
    rf"^share\s+{_KEY}\s+with\s+{_KEY}$", re.IGNORECASE
)
_TRADE = re.compile(
    rf"^trade\s+{_KEY}\s+to\s+{_KEY}\s+for\s+{_KEY}$",
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
