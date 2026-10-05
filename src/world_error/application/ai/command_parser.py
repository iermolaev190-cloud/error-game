"""Small deterministic command grammar used when the AI provider is unavailable."""

from __future__ import annotations

import re

from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.interpreter import IntentContext
from world_error.domain.shared.kernel import CharacterId

_MOVE = re.compile(r"^move\s+to\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE)
_INSPECT = re.compile(r"^inspect\s+([a-z][a-z0-9_-]*)$", re.IGNORECASE)


class CommandIntentParser:
    def interpret(self, raw_input: str, context: IntentContext) -> Intent | None:
        text = raw_input.strip()
        for pattern, intent_type in (
            (_MOVE, IntentType.MOVE),
            (_INSPECT, IntentType.INSPECT),
        ):
            match = pattern.fullmatch(text)
            if match is not None:
                target = match.group(1).lower()
                return Intent(type=intent_type, actor_id=CharacterId(context.character_id), target=target)
        return None
