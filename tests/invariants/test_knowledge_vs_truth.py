"""Инвариант: world truth ≠ player knowledge (требование 4 коммита 2).

TRUTH знает, что радио повреждено намеренно. Знание персонажа содержит только
то, что он мог наблюдать: «радио повреждено». Истина не переносится в знание ни
автоматически, ни через интерфейс.
"""

from __future__ import annotations

from typing import Tuple

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import CharacterId, DiscoveryState, LocationKey
from world_error.domain.world.instance import WorldInstance

FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")


def make_world_with_character(
    world_engine: WorldEngine, *, player_id: str = "player-1", chat_id: int = -1001
) -> Tuple[WorldInstance, CharacterId]:
    instance = world_engine.create_instance(telegram_chat_id=chat_id, seed=42)
    result = world_engine.create_character(instance.id, player_id=player_id, name="Аня")
    assert result.ok is True, result.error
    return instance, CharacterId(result.payload["character_id"])


def travel_to_old_station(
    world_engine: WorldEngine, instance: WorldInstance, character_id: CharacterId
) -> None:
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=FOREST
    ).ok
    assert world_engine.move_character(
        instance.id, character_id=character_id, to_location_key=OLD_STATION
    ).ok


def test_knowledge_holds_content_and_never_truth(
    world_engine: WorldEngine, catalog: ContentCatalog
) -> None:
    definition = catalog.information_definition("damaged_radio")
    assert "намеренно" in definition.truth
    assert "намеренно" not in definition.content

    instance, character_id = make_world_with_character(world_engine)
    travel_to_old_station(world_engine, instance, character_id)
    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )
    assert result.ok is True

    knowledge = list(world_engine.get_knowledge(instance.id, character_id))
    assert len(knowledge) == 1
    assert knowledge[0].claim == definition.content
    assert knowledge[0].claim != definition.truth
    assert "намеренно" not in knowledge[0].claim
    assert all(definition.truth not in item.claim for item in knowledge)

    # Мир получил только факт обнаружения, а не «истину как знание».
    information = world_engine.get_information(instance.id, "damaged_radio")
    assert information.discovery_state is DiscoveryState.DISCOVERED
    assert information.discovered_by == character_id


def test_result_payload_does_not_leak_truth(
    world_engine: WorldEngine, catalog: ContentCatalog
) -> None:
    definition = catalog.information_definition("damaged_radio")
    instance, character_id = make_world_with_character(world_engine)
    travel_to_old_station(world_engine, instance, character_id)

    result = world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="damaged_radio"
    )

    assert result.payload["claim"] == definition.content
    assert result.payload["external_url"] == "https://example.com/archive-17"
    assert all(
        definition.truth not in str(value) for value in result.payload.values()
    ), "канонический факт не должен попадать в результат действия"


def test_two_characters_get_independent_knowledge(
    world_engine: WorldEngine, catalog: ContentCatalog
) -> None:
    definition = catalog.information_definition("damaged_radio")
    instance, character_a = make_world_with_character(world_engine, player_id="player-1")
    second = world_engine.create_character(instance.id, player_id="player-2", name="Борис")
    assert second.ok is True, second.error
    character_b = CharacterId(second.payload["character_id"])

    travel_to_old_station(world_engine, instance, character_a)
    travel_to_old_station(world_engine, instance, character_b)

    first_discovery = world_engine.inspect_information(
        instance.id, character_id=character_a, target_key="damaged_radio"
    )
    second_discovery = world_engine.inspect_information(
        instance.id, character_id=character_b, target_key="damaged_radio"
    )
    assert first_discovery.ok is True and second_discovery.ok is True
    assert first_discovery.payload["already_known"] is False
    assert second_discovery.payload["already_known"] is False

    knowledge_a = list(world_engine.get_knowledge(instance.id, character_a))
    knowledge_b = list(world_engine.get_knowledge(instance.id, character_b))

    assert len(knowledge_a) == 1 and len(knowledge_b) == 1
    assert knowledge_a[0].id != knowledge_b[0].id
    assert knowledge_a[0].claim == knowledge_b[0].claim == definition.content
    assert knowledge_a[0].subject_id == str(character_a)
    assert knowledge_b[0].subject_id == str(character_b)
    assert knowledge_a[0].subject_type is SubjectType.CHARACTER

    # Первый нашедший не перезаписывается вторым.
    information = world_engine.get_information(instance.id, "damaged_radio")
    assert information.discovered_by == character_a


def test_knowledge_is_scoped_to_its_instance(world_engine: WorldEngine) -> None:
    world_a, character_a = make_world_with_character(world_engine, chat_id=-1001)
    world_b, character_b = make_world_with_character(
        world_engine, player_id="player-2", chat_id=-1002
    )
    travel_to_old_station(world_engine, world_a, character_a)
    travel_to_old_station(world_engine, world_b, character_b)

    assert world_engine.inspect_information(
        world_a.id, character_id=character_a, target_key="damaged_radio"
    ).ok

    assert len(list(world_engine.get_knowledge(world_a.id, character_a))) == 1
    assert list(world_engine.get_knowledge(world_b.id, character_b)) == []
    assert (
        world_engine.get_information(world_b.id, "damaged_radio").discovery_state
        is DiscoveryState.UNDISCOVERED
    )
