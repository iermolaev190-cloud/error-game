"""Bounded, immutable context supplied to an NPC dialogue provider."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NpcKnowledgeContext:
    claim: str
    claim_type: str
    confidence: str


@dataclass(frozen=True, slots=True)
class NpcDialogueContext:
    npc_key: str
    npc_name: str
    npc_description: str
    # npc_goals: tuple[str, ...] = ()
    # Empty in commit 13. NpcDefinition has no visibility marker.
    # Will be filled when goal visibility model is added.
    current_location_key: str
    knowledge: tuple[NpcKnowledgeContext, ...]
    recent_history: tuple[str, ...]
    npc_goals: tuple[str, ...] = ()
