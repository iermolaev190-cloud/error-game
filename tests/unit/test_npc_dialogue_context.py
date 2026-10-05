from dataclasses import FrozenInstanceError, fields

import pytest

from world_error.application.ai.npc_context import NpcDialogueContext, NpcKnowledgeContext
from world_error.application.ai.npc_context_builder import NpcDialogueContextBuilder


def test_npc_dialogue_context_is_bounded_and_frozen() -> None:
    context = NpcDialogueContext(
        npc_key="caretaker",
        npc_name="Caretaker",
        npc_description="Keeps the base running.",
        current_location_key="base",
        knowledge=(NpcKnowledgeContext("The generator is damaged.", "FACT", "LIKELY"),),
        recent_history=("Player: Hello.", "NPC: Hello."),
    )

    names = {field.name for field in fields(NpcDialogueContext)}
    assert names == {
        "npc_key",
        "npc_name",
        "npc_description",
        "npc_goals",
        "current_location_key",
        "knowledge",
        "recent_history",
    }
    assert "world_instance_id" not in names
    assert context.npc_goals == ()
    assert context.knowledge[0].claim == "The generator is damaged."
    with pytest.raises(FrozenInstanceError):
        context.npc_name = "Changed"


def test_context_builder_includes_only_selected_npc_knowledge(world_engine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-7001, seed=7)
    npcs = {npc.key: npc for npc in world_engine.get_npcs(instance.id)}
    mechanic = npcs["mechanic"]
    scout = npcs["scout"]
    assert world_engine.npc_learn(
        instance.id,
        npc_id=mechanic.id,
        information_key="damaged_radio",
        claim="The radio is damaged.",
    ).ok
    assert world_engine.npc_learn(
        instance.id,
        npc_id=scout.id,
        information_key="dispatch_log",
        claim="I hid the secret map.",
    ).ok

    context = NpcDialogueContextBuilder(world_engine).build_npc_dialogue_context(
        instance.id,
        mechanic.id,
        ("one", "two", "three", "four", "five", "six"),
    )

    assert context.npc_key == "mechanic"
    assert context.npc_goals == ()
    assert tuple(item.claim for item in context.knowledge) == ("The radio is damaged.",)
    assert context.recent_history == ("two", "three", "four", "five", "six")
    assert not hasattr(context, "world_instance_id")
