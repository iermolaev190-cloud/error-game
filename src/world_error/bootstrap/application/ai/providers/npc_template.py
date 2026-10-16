"""Fact-free dialogue fallback when no NPC dialogue provider is available."""

from __future__ import annotations

from world_error.application.ai.npc_context import NpcDialogueContext


class TemplateNpcDialogueProvider:
    def generate_reply(
        self, npc_context: NpcDialogueContext, message: str
    ) -> str:
        del npc_context, message
        return "Я не знаю."
