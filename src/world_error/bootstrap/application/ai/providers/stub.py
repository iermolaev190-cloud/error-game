"""Unavailable provider used until a real LLM integration is approved."""

from __future__ import annotations

from world_error.application.ai.interpreter import IntentContext


class StubIntentProvider:
    def interpret(self, raw_input: str, context: IntentContext):
        del raw_input, context
        raise NotImplementedError("AI intent provider is not configured")
