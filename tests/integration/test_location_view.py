"""Integration: `list_by_location` и публичная проекция локации."""

from __future__ import annotations

import dataclasses
from typing import Callable

import pytest

from world_error.application.queries.location_view import (
    CharacterPresence,
    ItemPresence,
    LocationView,
    NpcPresence,
)
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import CharacterActivity, CharacterLifecycle
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.items.item import ItemVisibility
from world_error.domain.npcs.npc import NpcStatus
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    LocationKey,
)
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

BASE = LocationKey("base")
FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")
TRUTH_FRAGMENT = "намеренно"


def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def make_character(
    world_engine: WorldEngine, instance: WorldInstance, player_id: str
) -> CharacterId:
    result = world_engine.create_character(instance.id, player_id=player_id, name=player_id)
    assert result.ok is True, result.error
    return CharacterId(result.payload["character_id"])


def travel_to_station(
    world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId
) -> None:
    for target in (FOREST, OLD_STATION):
        result = world_engine.move_character(
            instance.id, character_id=character_id, to_location_key=target
        )
        assert result.ok is True, result.error


def test_list_by_location_is_scoped_to_instance_and_location(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    world_one = make_world(world_engine, chat_id=-1001)
    world_two = make_world(world_engine, chat_id=-1002)
    base_one = make_character(world_engine, world_one, "player-a")
    station_one = make_character(world_engine, world_one, "player-b")
    travel_to_station(world_engine, world_one, station_one)
    base_two = make_character(world_engine, world_two, "player-c")

    with uow_factory() as uow:
        assert [c.id for c in uow.characters.list_by_location(world_one.id, BASE)] == [base_one]
        assert [
            c.id for c in uow.characters.list_by_location(world_one.id, OLD_STATION)
        ] == [station_one]
        assert list(uow.characters.list_by_location(world_one.id, FOREST)) == []
        assert [c.id for c in uow.characters.list_by_location(world_two.id, BASE)] == [base_two]
        assert list(uow.characters.list_by_location(world_two.id, OLD_STATION)) == []


def test_location_view_contains_public_facts(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    first = make_character(world_engine, instance, "player-a")
    second = make_character(world_engine, instance, "player-b")
    travel_to_station(world_engine, instance, first)
    travel_to_station(world_engine, instance, second)

    view = world_engine.view_location(instance.id, observer_id=first, location_key=OLD_STATION)

    assert view.world_instance_id == str(instance.id)
    assert view.location_key == "old_station"
    assert view.name == "Старая станция"
    assert view.type == "ABANDONED_FACILITY"
    assert view.description
    assert view.discovery_state == "DISCOVERED"
    assert {presence.character_id for presence in view.characters} == {str(first), str(second)}
    assert all(presence.activity == "ACTIVE" for presence in view.characters)
    assert all(presence.name for presence in view.characters)
    assert {item.key for item in view.items} == {"flashlight", "credits"}
    assert all(item.name for item in view.items)
    assert all(not hasattr(item, "owner_id") for item in view.items)


def test_location_view_has_no_knowledge_or_truth_fields(
    world_engine: WorldEngine, catalog: ContentCatalog
) -> None:
    """Структурная гарантия: в проекции нет полей знания и truth."""
    assert {field.name for field in dataclasses.fields(LocationView)} == {
        "world_instance_id",
        "location_key",
        "name",
        "type",
        "description",
        "discovery_state",
        "characters",
        "npcs",
        "items",
    }
    assert {field.name for field in dataclasses.fields(CharacterPresence)} == {
        "character_id",
        "name",
        "activity",
    }
    assert {field.name for field in dataclasses.fields(NpcPresence)} == {
        "npc_id",
        "name",
        "status",
    }
    assert {field.name for field in dataclasses.fields(ItemPresence)} == {"key", "name"}

    definition = catalog.information_definition("damaged_radio")
    instance = make_world(world_engine)
    first = make_character(world_engine, instance, "player-a")
    travel_to_station(world_engine, instance, first)
    assert world_engine.inspect_information(
        instance.id, character_id=first, target_key="damaged_radio"
    ).ok is True

    view = world_engine.view_location(instance.id, observer_id=first, location_key=OLD_STATION)
    rendered = repr(view)
    assert definition.truth not in rendered
    assert definition.content not in rendered
    assert TRUTH_FRAGMENT not in rendered


def test_location_view_hides_secret_items_and_owner_fields(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork], catalog: ContentCatalog
) -> None:
    from dataclasses import replace

    secret_catalog = replace(
        catalog,
        items={
            **catalog.items,
            "flashlight": replace(catalog.item_definition("flashlight"), visibility=ItemVisibility.SECRET),
        },
    )
    world_engine = WorldEngine(uow_factory=uow_factory, catalog=secret_catalog)
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")
    assert world_engine.move_character(
        instance.id, character_id=observer, to_location_key=FOREST
    ).ok is True

    view = world_engine.view_location(instance.id, observer_id=observer, location_key=FOREST)

    assert {item.key for item in view.items} == {"medkit"}
    assert {field.name for field in dataclasses.fields(ItemPresence)} == {"key", "name"}
    assert "owner_id" not in repr(view)


def test_location_view_requires_observer_in_location(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")  # остаётся в BASE

    with pytest.raises(DomainError) as exc_info:
        world_engine.view_location(instance.id, observer_id=observer, location_key=OLD_STATION)
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_location_view_unknown_location_is_not_found(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")

    with pytest.raises(DomainError) as exc_info:
        world_engine.view_location(
            instance.id, observer_id=observer, location_key=LocationKey("nowhere")
        )
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_location_view_rejects_dead_observer(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")
    cause_event_id = world_engine.get_events(instance.id)[-1].id
    death = world_engine.kill_character(instance.id, observer, cause_event_id=cause_event_id)
    assert death.ok is True, death.error

    with pytest.raises(DomainError) as exc_info:
        world_engine.view_location(instance.id, observer_id=observer, location_key=BASE)
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_location_view_does_not_change_state(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")
    state_before = world_engine.get_instance(instance.id).state
    events_before = len(world_engine.get_events(instance.id))

    world_engine.view_location(instance.id, observer_id=observer, location_key=BASE)
    world_engine.view_location(instance.id, observer_id=observer, location_key=BASE)

    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )
    assert len(world_engine.get_events(instance.id)) == events_before


def test_location_view_is_discovered_for_present_observer(world_engine: WorldEngine) -> None:
    """Наблюдатель физически в локации → она не может быть UNDISCOVERED."""
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")

    base_view = world_engine.view_location(instance.id, observer_id=observer, location_key=BASE)
    assert base_view.discovery_state == "DISCOVERED"

    assert world_engine.move_character(
        instance.id, character_id=observer, to_location_key=FOREST
    ).ok is True
    forest_view = world_engine.view_location(instance.id, observer_id=observer, location_key=FOREST)
    assert forest_view.discovery_state == "DISCOVERED"


def test_location_view_lists_characters_with_any_activity(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")
    other = make_character(world_engine, instance, "player-b")

    with uow_factory() as uow:
        character = uow.characters.get(instance.id, other)
        character.activity = CharacterActivity.MISSING
        uow.characters.save(character)
        uow.commit()

    view = world_engine.view_location(instance.id, observer_id=observer, location_key=BASE)
    activities = {presence.character_id: presence.activity for presence in view.characters}
    assert activities[str(other)] == "MISSING"
    assert activities[str(observer)] == "ACTIVE"


def test_location_view_shows_npcs_with_public_facts_only(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")

    view = world_engine.view_location(instance.id, observer_id=observer, location_key=BASE)

    assert len(view.npcs) == 1
    assert view.npcs[0].name == "Смотритель"
    assert view.npcs[0].status == "ACTIVE"

    rendered = repr(view)
    # Ни целей, ни описания NPC, ни знания в проекции нет.
    assert "KEEP_BASE_RUNNING" not in rendered
    assert "HIDE_OLD_MISTAKE" not in rendered
    assert "не любит лишних вопросов" not in rendered


def test_missing_npc_is_hidden_in_every_location(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    observer = make_character(world_engine, instance, "player-a")
    caretaker = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == "caretaker")

    assert world_engine.npc_change_status(
        instance.id, npc_id=caretaker.id, to_status=NpcStatus.MISSING
    ).ok is True

    base_view = world_engine.view_location(instance.id, observer_id=observer, location_key=BASE)
    assert {presence.npc_id for presence in base_view.npcs} == set()

    assert world_engine.move_character(
        instance.id, character_id=observer, to_location_key=FOREST
    ).ok is True
    forest_view = world_engine.view_location(instance.id, observer_id=observer, location_key=FOREST)
    assert caretaker.id not in {presence.npc_id for presence in forest_view.npcs}
    assert {presence.name for presence in forest_view.npcs} == {"Разведчик"}

    assert world_engine.move_character(
        instance.id, character_id=observer, to_location_key=OLD_STATION
    ).ok is True
    station_view = world_engine.view_location(
        instance.id, observer_id=observer, location_key=OLD_STATION
    )
    assert caretaker.id not in {presence.npc_id for presence in station_view.npcs}
    assert {presence.name for presence in station_view.npcs} == {"Механик"}
