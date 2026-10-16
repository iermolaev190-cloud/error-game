"""Invariants for optional external information links and instance isolation."""

from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.interfaces.telegram.formatter import TelegramFormatter

FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")


def _make_world_with_character(world_engine, *, chat_id: int, player_id: str):
    instance = world_engine.create_instance(telegram_chat_id=chat_id, seed=chat_id)
    created = world_engine.create_character(
        instance.id, player_id=player_id, name=player_id
    )
    assert created.ok, created.error
    return instance, CharacterId(created.payload["character_id"])


def _travel_to_station(world_engine, instance, character_id: CharacterId) -> None:
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=FOREST
    ).ok
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=OLD_STATION
    ).ok


def test_inspect_without_external_url_omits_link_from_payload_and_telegram(
    world_engine,
) -> None:
    instance, character_id = _make_world_with_character(
        world_engine, chat_id=-9301, player_id="unlinked-player"
    )
    _travel_to_station(world_engine, instance, character_id)

    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="station_test_log"
    )

    assert result.ok
    assert "external_url" not in result.payload
    assert "Ссылка" not in TelegramFormatter().format_dm(result)


def test_external_url_content_does_not_leak_instance_state(world_engine) -> None:
    world_a, character_a = _make_world_with_character(
        world_engine, chat_id=-9302, player_id="player-a"
    )
    world_b, character_b = _make_world_with_character(
        world_engine, chat_id=-9303, player_id="player-b"
    )
    _travel_to_station(world_engine, world_a, character_a)
    _travel_to_station(world_engine, world_b, character_b)
    events_b_before = list(world_engine.get_events(world_b.id))
    state_b_before = world_engine.get_instance(world_b.id).state

    result_a = world_engine.inspect_information(
        world_a.id, character_id=character_a, target_key="damaged_radio"
    )

    assert result_a.ok
    assert result_a.payload["external_url"] == "https://example.com/archive-17"
    assert not list(world_engine.get_knowledge(world_b.id, character_b))
    assert (
        world_engine.get_information(world_b.id, "damaged_radio").discovered_by
        is None
    )
    assert list(world_engine.get_events(world_b.id)) == events_b_before
    state_b_after = world_engine.get_instance(world_b.id).state
    assert (state_b_after.world_tick, state_b_after.state_version) == (
        state_b_before.world_tick,
        state_b_before.state_version,
    )
    assert all(
        event.world_instance_id == world_b.id
        for event in world_engine.get_events(world_b.id)
    )

    result_b = world_engine.inspect_information(
        world_b.id, character_id=character_b, target_key="damaged_radio"
    )
    assert result_b.ok
    assert result_b.payload["external_url"] == result_a.payload["external_url"]


def test_inspect_cannot_resolve_character_from_another_instance(world_engine) -> None:
    world_a, character_a = _make_world_with_character(
        world_engine, chat_id=-9304, player_id="scoped-player-a"
    )
    world_b, character_b = _make_world_with_character(
        world_engine, chat_id=-9305, player_id="scoped-player-b"
    )
    _travel_to_station(world_engine, world_a, character_a)
    _travel_to_station(world_engine, world_b, character_b)
    events_a_before = list(world_engine.get_events(world_a.id))
    events_b_before = list(world_engine.get_events(world_b.id))

    result = world_engine.inspect_information(
        world_a.id, character_id=character_b, target_key="damaged_radio"
    )

    assert not result.ok
    assert "external_url" not in result.payload
    assert list(world_engine.get_events(world_a.id)) == events_a_before
    assert list(world_engine.get_events(world_b.id)) == events_b_before
    assert (
        world_engine.get_information(world_b.id, "damaged_radio").discovered_by
        is None
    )
