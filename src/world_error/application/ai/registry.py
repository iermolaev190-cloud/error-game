"""Player-facing intent routing table.

Only player intents are exposed here. System methods (pump, schedule, npc_*,
etc.) are NOT exposed here. They are called by world engine internals.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from world_error.application.ai.intent import IntentType


@dataclass(frozen=True, slots=True)
class ResolvedHandler:
    method_name: str
    actor_param: str
    target_param: str | None


INTENT_HANDLERS: Mapping[IntentType, ResolvedHandler] = MappingProxyType(
    {
        IntentType.MOVE: ResolvedHandler("move_character", "character_id", "to_location_key"),
        IntentType.TRAVEL: ResolvedHandler("begin_travel", "character_id", "to_location_key"),
        IntentType.INSPECT: ResolvedHandler("inspect_information", "character_id", "target_key"),
        IntentType.SHARE_KNOWLEDGE: ResolvedHandler("share_knowledge", "sharer_id", "information_key"),
        IntentType.TAKE: ResolvedHandler("take_item", "character_id", "item_id"),
        IntentType.DROP: ResolvedHandler("drop_item", "character_id", "item_id"),
        IntentType.TRADE: ResolvedHandler("trade_items", "initiator_id", None),
        IntentType.GIVE: ResolvedHandler("give_item", "giver_id", "receiver_id"),
        IntentType.LINK_EVIDENCE: ResolvedHandler("link_evidence", "actor_id", "information_id"),
        IntentType.CREATE_THEORY: ResolvedHandler("create_theory", "author_id", "case_id"),
        IntentType.LINK_THEORY_EVIDENCE: ResolvedHandler("link_theory_evidence", "actor_id", "theory_id"),
        IntentType.MARK_CONTRADICTION: ResolvedHandler("mark_contradiction", "actor_id", "evidence_a_id"),
        IntentType.MARK_SUSPECT: ResolvedHandler("mark_suspect", "actor_id", "subject_id"),
        IntentType.ADD_CASE_NOTE: ResolvedHandler("add_case_note", "author_id", "case_id"),
        IntentType.ADD_CASE_QUESTION: ResolvedHandler("add_case_question", "added_by", "case_id"),
        IntentType.CLOSE_CASE: ResolvedHandler("close_case", "actor_id", "case_id"),
        IntentType.INSPECT_LEGACY: ResolvedHandler("inspect_legacy_document", "character_id", "document_id"),
        IntentType.LEAVE_LEGACY: ResolvedHandler("leave_legacy_document", "character_id", "document_key"),
    }
)


def resolve_handler(intent_type: object) -> ResolvedHandler | None:
    if not isinstance(intent_type, IntentType):
        return None
    return INTENT_HANDLERS.get(intent_type)
