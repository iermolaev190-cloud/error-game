"""Document dates are player knowledge metadata, never world truth."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.shared.kernel import CharacterId, LocationKey


def test_inspect_exposes_document_date_without_exposing_truth(
    uow_factory, catalog
) -> None:  # noqa: ANN001
    document_date = date(2024, 3, 15)
    information = dict(catalog.information)
    information["damaged_radio"] = replace(
        catalog.information_definition("damaged_radio"), document_date=document_date
    )
    dated_catalog = ContentCatalog.build(
        version=catalog.version,
        start_location=catalog.start_location,
        locations=catalog.locations,
        information=information,
        items=catalog.items,
        npcs=catalog.npcs,
            cases=catalog.cases,
        rules=catalog.rules,
    )
    world_engine = WorldEngine(uow_factory=uow_factory, catalog=dated_catalog)
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    character = world_engine.create_character(instance.id, player_id="player-a", name="Аня")
    character_id = CharacterId(character.payload["character_id"])
    world_engine.move_character(
        instance.id,
        character_id=character_id,
        to_location_key=LocationKey("forest"),
    )
    world_engine.move_character(
        instance.id,
        character_id=character_id,
        to_location_key=LocationKey("old_station"),
    )

    inspected = world_engine.inspect_information(
        instance.id,
        character_id=character_id,
        target_key="damaged_radio",
    )

    assert inspected.ok is True, inspected.error
    assert inspected.payload["document_date"] == "2024-03-15"
    assert "намеренно" not in inspected.payload["claim"]
    knowledge = world_engine.get_knowledge(
        instance.id,
        character_id,
    )
    assert knowledge[0].document_date == document_date