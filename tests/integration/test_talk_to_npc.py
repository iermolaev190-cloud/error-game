import pytest

from world_error.application.ai.providers.npc_mock import MockNpcDialogueProvider
from world_error.domain.npcs.npc import NpcStatus
from world_error.domain.shared.kernel import CharacterId, LocationKey


@pytest.mark.parametrize(
    ("npc_key", "reply"),
    (
        ("caretaker", "The base is quiet."),
        ("mechanic", "I am repairing the station."),
        ("scout", "The forest is calm."),
    ),
)
def test_talk_to_real_content_npc_is_read_only(
    make_world_engine, npc_key: str, reply: str
) -> None:
    provider = MockNpcDialogueProvider({(npc_key, "hello"): reply})
    engine = make_world_engine(provider)
    instance = engine.create_instance(telegram_chat_id=-8101, seed=81)
    npc = next(npc for npc in engine.get_npcs(instance.id) if npc.key == npc_key)
    created = engine.create_character(
        instance.id,
        player_id=f"player-{npc_key}",
        name="Player",
        location_key=LocationKey(str(npc.location_key)),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])

    state_before = engine.get_instance(instance.id).state
    events_before = tuple(engine.get_events(instance.id))
    result = engine.talk_to_npc(
        instance.id,
        character_id=character_id,
        npc_id=npc.id,
        message="hello",
    )

    assert result.ok, result.error
    assert result.payload["reply"] == reply
    assert engine.get_instance(instance.id).state == state_before
    assert tuple(engine.get_events(instance.id)) == events_before


def test_talking_to_npc_in_another_location_fails(make_world_engine) -> None:
    engine = make_world_engine()
    instance = engine.create_instance(telegram_chat_id=-8102, seed=82)
    created = engine.create_character(instance.id, player_id="alice", name="Alice")
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    scout = next(npc for npc in engine.get_npcs(instance.id) if npc.key == "scout")
    state_before = engine.get_instance(instance.id).state
    events_before = tuple(engine.get_events(instance.id))

    result = engine.talk_to_npc(
        instance.id,
        character_id=character_id,
        npc_id=scout.id,
        message="hello",
    )

    assert not result.ok
    assert result.error is not None
    assert engine.get_instance(instance.id).state == state_before
    assert tuple(engine.get_events(instance.id)) == events_before


def test_talking_to_inactive_npc_fails(make_world_engine) -> None:
    engine = make_world_engine()
    instance = engine.create_instance(telegram_chat_id=-8103, seed=83)
    created = engine.create_character(instance.id, player_id="alice", name="Alice")
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    caretaker = next(
        npc for npc in engine.get_npcs(instance.id) if npc.key == "caretaker"
    )
    status = engine.npc_change_status(
        instance.id,
        npc_id=caretaker.id,
        to_status=NpcStatus.MISSING,
    )
    assert status.ok, status.error
    events_before = tuple(engine.get_events(instance.id))
    state_before = engine.get_instance(instance.id).state

    result = engine.talk_to_npc(
        instance.id,
        character_id=character_id,
        npc_id=caretaker.id,
        message="hello",
    )

    assert not result.ok
    assert result.error is not None
    assert engine.get_instance(instance.id).state == state_before
    assert tuple(engine.get_events(instance.id)) == events_before
