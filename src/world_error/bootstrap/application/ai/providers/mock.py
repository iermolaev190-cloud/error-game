"""Deterministic frozen-response provider for tests and local development."""

from __future__ import annotations

from typing import Mapping

from world_error.application.ai.intent import Intent
from world_error.application.ai.interpreter import IntentContext


class MockIntentProvider:
    def __init__(self, responses: Mapping[str, Intent] | None = None) -> None:
        self._responses = dict(responses or {})

    def interpret(self, raw_input: str, context: IntentContext) -> Intent | None:
        del context
        return self._responses.get(raw_input)
