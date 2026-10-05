from dataclasses import FrozenInstanceError, fields

import pytest

from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.registry import INTENT_HANDLERS, ResolvedHandler, resolve_handler
from world_error.domain.shared.kernel import CharacterId


EXPECTED_HANDLERS = {
    IntentType.MOVE: ("move_character", "character_id", "to_location_key"),
    IntentType.TRAVEL: ("begin_travel", "character_id", "to_location_key"),
    IntentType.INSPECT: ("inspect_information", "character_id", "target_key"),
    IntentType.SHARE_KNOWLEDGE: ("share_knowledge", "sharer_id", "information_key"),
    IntentType.TAKE: ("take_item", "character_id", "item_id"),
    IntentType.DROP: ("drop_item", "character_id", "item_id"),
    IntentType.TRADE: ("trade_items", "initiator_id", None),
    IntentType.GIVE: ("give_item", "giver_id", "receiver_id"),
    IntentType.LINK_EVIDENCE: ("link_evidence", "actor_id", "information_id"),
    IntentType.CREATE_THEORY: ("create_theory", "author_id", "case_id"),
    IntentType.LINK_THEORY_EVIDENCE: ("link_theory_evidence", "actor_id", "theory_id"),
    IntentType.MARK_CONTRADICTION: ("mark_contradiction", "actor_id", "evidence_a_id"),
    IntentType.MARK_SUSPECT: ("mark_suspect", "actor_id", "subject_id"),
    IntentType.ADD_CASE_NOTE: ("add_case_note", "author_id", "case_id"),
    IntentType.ADD_CASE_QUESTION: ("add_case_question", "added_by", "case_id"),
    IntentType.CLOSE_CASE: ("close_case", "actor_id", "case_id"),
    IntentType.INSPECT_LEGACY: ("inspect_legacy_document", "character_id", "document_id"),
    IntentType.LEAVE_LEGACY: ("leave_legacy_document", "character_id", "document_key"),
}

SYSTEM_METHODS = {
    "create_instance",
    "create_character",
    "spawn_new_character",
    "advance_tick",
    "change_status",
    "record_time_point",
    "kill_character",
    "die_character",
    "npc_move",
    "npc_learn",
    "npc_observe_information",
    "npc_change_status",
    "change_relationship",
    "change_faction_status",
    "apply_significant_action",
    "schedule_consequence",
    "cancel_consequence",
    "transform_consequence",
    "schedule_event",
    "pump_time",
    "pump_consequences",
    "pump_scheduled_events",
}


def test_intent_is_frozen_and_requires_type_and_actor() -> None:
    intent = Intent(type=IntentType.MOVE, actor_id=CharacterId("ch_player"), target="forest")

    assert intent.target == "forest"
    assert dict(intent.params) == {}
    with pytest.raises(FrozenInstanceError):
        intent.target = "base"  # type: ignore[misc]
    with pytest.raises(TypeError):
        intent.params["extra"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        Intent(actor_id=CharacterId("ch_player"))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Intent(type=IntentType.MOVE)  # type: ignore[call-arg]


def test_intent_enum_has_exactly_eighteen_player_actions() -> None:
    assert len(IntentType) == 18
    assert set(INTENT_HANDLERS) == set(IntentType)
    assert all(isinstance(item, ResolvedHandler) for item in INTENT_HANDLERS.values())
    assert {
        intent_type: (handler.method_name, handler.actor_param, handler.target_param)
        for intent_type, handler in INTENT_HANDLERS.items()
    } == EXPECTED_HANDLERS


def test_system_methods_are_not_exposed_as_intents() -> None:
    assert SYSTEM_METHODS.isdisjoint(
        handler.method_name for handler in INTENT_HANDLERS.values()
    )


def test_resolve_handler_rejects_unknown_type() -> None:
    assert resolve_handler("PUMP_CONSEQUENCES") is None
    assert resolve_handler(None) is None


def test_intent_has_no_world_instance_id_field() -> None:
    assert "world_instance_id" not in {item.name for item in fields(Intent)}
