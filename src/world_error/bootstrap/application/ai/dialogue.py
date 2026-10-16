"""Provider contract for NPC dialogue generation."""

from __future__ import annotations

from typing import Protocol

from world_error.application.ai.npc_context import NpcDialogueContext


class NpcDialogueProvider(Protocol):
    def generate_reply(
        self, npc_context: NpcDialogueContext, message: str
    ) -> str | None: ...
