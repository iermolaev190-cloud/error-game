"""Frozen-response provider for NPC dialogue tests and local development."""

from __future__ import annotations

from typing import Mapping

from world_error.application.ai.npc_context import NpcDialogueContext


class MockNpcDialogueProvider:
    def __init__(
        self, responses: Mapping[tuple[str, str], str | None] | None = None
    ) -> None:
        self._responses = dict(responses or {})

    def generate_reply(
        self, npc_context: NpcDialogueContext, message: str
    ) -> str | None:
        return self._responses.get((npc_context.npc_key, message))
