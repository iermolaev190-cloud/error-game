"""Build a provider-safe dialogue context from one instance-scoped NPC."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from world_error.application.ai.npc_context import NpcDialogueContext, NpcKnowledgeContext
from world_error.domain.shared.kernel import NpcId, WorldInstanceId

if TYPE_CHECKING:
    from world_error.application.services.world_engine import WorldEngine


class NpcDialogueContextBuilder:
    def __init__(self, world_engine: WorldEngine) -> None:
        self._world_engine = world_engine

    def build_npc_dialogue_context(
        self,
        world_instance_id: WorldInstanceId,
        npc_id: NpcId,
        recent_history: Sequence[str] = (),
    ) -> NpcDialogueContext:
        npc = self._world_engine.get_npc(world_instance_id, npc_id)
        definition = self._world_engine.get_npc_definition(npc.key)
        knowledge = self._world_engine.get_npc_knowledge(world_instance_id, npc_id)

        return NpcDialogueContext(
            npc_key=definition.key,
            npc_name=definition.name,
            npc_description=definition.description,
            npc_goals=(),
            current_location_key=str(npc.location_key),
            knowledge=tuple(
                NpcKnowledgeContext(
                    claim=record.claim,
                    claim_type=record.claim_type.value,
                    confidence=record.confidence.value,
                )
                for record in knowledge
            ),
            recent_history=tuple(recent_history[-5:]),
        )
