"""Unavailable NPC dialogue provider used until a real model is approved."""

from __future__ import annotations

from world_error.application.ai.npc_context import NpcDialogueContext


class StubNpcDialogueProvider:
    def generate_reply(
        self, npc_context: NpcDialogueContext, message: str
    ) -> str | None:
        del npc_context, message
        raise NotImplementedError("NPC dialogue provider is not configured")
