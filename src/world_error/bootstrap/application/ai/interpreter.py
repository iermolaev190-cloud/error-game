"""Interfaces for bounded intent interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from world_error.application.ai.intent import Intent
from world_error.domain.shared.kernel import CharacterId


@dataclass(frozen=True, slots=True)
class IntentContext:
    player_id: str
    character_id: CharacterId
    location_id: str
    visible_objects: tuple[str, ...]
    allowed_actions: tuple[str, ...]


class IntentInterpreter(Protocol):
    def interpret(self, raw_input: str, context: IntentContext) -> Intent | None: ...


class IntentProvider(Protocol):
    def interpret(self, raw_input: str, context: IntentContext) -> Intent | None: ...


class FallbackIntentInterpreter:
    """Use a provider when available, otherwise parse a limited command grammar."""

    def __init__(self, provider: IntentProvider, fallback: IntentInterpreter) -> None:
        self._provider = provider
        self._fallback = fallback

    def interpret(self, raw_input: str, context: IntentContext) -> Intent | None:
        try:
            intent = self._provider.interpret(raw_input, context)
        except NotImplementedError:
            intent = None
        if intent is not None and intent.type.value in context.allowed_actions:
            return intent
        fallback_intent = self._fallback.interpret(raw_input, context)
        if fallback_intent is not None and fallback_intent.type.value in context.allowed_actions:
            return fallback_intent
        return None
