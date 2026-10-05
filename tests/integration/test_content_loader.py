"""Integration: загрузка контента из файлов и её ошибки."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from world_error.domain.content.catalog import ContentError
from world_error.infrastructure.content.loader import load_content_catalog

LOCATION: dict[str, Any] = {
    "key": "base",
    "name": "Лагерь",
    "type": "BASE",
    "description": "Описание лагеря.",
    "connections": [],
}

INFORMATION: dict[str, Any] = {
    "key": "clue",
    "location_key": "base",
    "type": "DEVICE",
    "source": "PHYSICAL_OBJECT",
    "authenticity": "AUTHENTIC",
    "access": "OPEN",
    "content": "Корпус вскрыт.",
    "truth": "Корпус вскрыт намеренно.",
}

NPC: dict[str, Any] = {
    "key": "caretaker",
    "name": "Смотритель",
    "description": "Описание NPC.",
    "initial_location": "base",
    "goals": ["KEEP_BASE_RUNNING"],
}

FACTION: dict[str, Any] = {
    "key": "expedition",
    "name": "Экспедиция",
    "description": "Исследовательская группа.",
    "type": "SCIENTIFIC",
    "public_goal": "Исследовать станцию.",
    "locations": ["base"],
    "hidden_goal": "Скрыть результаты.",
}

ITEM: dict[str, Any] = {
    "key": "medkit",
    "name": "Аптечка",
    "description": "Расходуемый медицинский набор.",
    "weight": 250,
    "type": "CONSUMABLE",
    "stackable": True,
    "unique": False,
    "visibility": "PUBLIC",
}

CASE: dict[str, Any] = {
    "key": "station_signal",
    "question": "Почему пропала связь со станцией?",
    "opening_hint": "Связь пропала во время выхода исследователя.",
    "initial_evidence": [{"information_key": "clue", "relevance": "UNKNOWN"}],
    "resolution_criteria": {
        "required_evidence_count": 1,
        "required_theory_count": 1,
        "required_theory_min_confidence": "PLAUSIBLE",
        "required_distinct_contributors": 2,
        "required_actions": ["mark_suspect"],
    },
}


def write_content(
    root: Path,
    *,
    manifest: dict[str, Any] | None = None,
    locations: list[dict[str, Any]] | None = None,
    information: list[dict[str, Any]] | None = None,
    npcs: list[dict[str, Any]] | None = None,
    factions: list[dict[str, Any]] | None = None,
    items: list[dict[str, Any]] | None = None,
    cases: list[dict[str, Any]] | None = None,
) -> Path:
    (root / "locations").mkdir(parents=True, exist_ok=True)
    (root / "information").mkdir(parents=True, exist_ok=True)
    payload = manifest if manifest is not None else {"version": "v1", "start_location": "base"}
    (root / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    for index, item in enumerate(locations or []):
        name = f"{index:02d}_{item.get('key', 'location')}.json"
        (root / "locations" / name).write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    for index, item in enumerate(information or []):
        name = f"{index:02d}_{item.get('key', 'information')}.json"
        (root / "information" / name).write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    if npcs is not None:
        (root / "npcs").mkdir(parents=True, exist_ok=True)
        for index, item in enumerate(npcs):
            name = f"{index:02d}_{item.get('key', 'npc')}.json"
            (root / "npcs" / name).write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
    if factions is not None:
        (root / "factions").mkdir(parents=True, exist_ok=True)
        for index, item in enumerate(factions):
            name = f"{index:02d}_{item.get('key', 'faction')}.json"
            (root / "factions" / name).write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8"
            )
    if items is not None:
        (root / "items").mkdir(parents=True, exist_ok=True)
        for index, item in enumerate(items):
            name = f"{index:02d}_{item.get('key', 'item')}.json"
            (root / "items" / name).write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8"
            )
    if cases is not None:
        (root / "cases").mkdir(parents=True, exist_ok=True)
        for index, item in enumerate(cases):
            name = f"{index:02d}_{item.get('key', 'case')}.json"
            (root / "cases" / name).write_text(
                json.dumps(item, ensure_ascii=False), encoding="utf-8"
            )
    return root


def test_loads_repository_content(content_dir: Path) -> None:
    catalog = load_content_catalog(content_dir)
    assert catalog.version == "v1"
    assert set(catalog.locations) == {"base", "forest", "old_station"}
    assert set(catalog.information) == {
        "damaged_radio",
        "dispatch_log",
        "station_test_log",
    }
    assert catalog.information_definition("damaged_radio").truth.endswith("инструментом.")
    assert set(catalog.cases) == {"station_signal"}
    assert catalog.case_definition("station_signal").initial_evidence[0].information_key == "damaged_radio"


def test_loads_minimal_content(tmp_path: Path) -> None:
    catalog = load_content_catalog(
        write_content(tmp_path / "content", locations=[LOCATION], information=[INFORMATION])
    )
    assert catalog.start_location == "base"
    assert catalog.location("base").name == "Лагерь"
    assert catalog.information_definition("clue").content == "Корпус вскрыт."


def test_content_without_item_definitions_or_spawns_is_valid(tmp_path: Path) -> None:
    catalog = load_content_catalog(write_content(tmp_path / "c", locations=[LOCATION]))
    assert catalog.items == {}
    assert catalog.location("base").items == ()


def test_content_without_cases_directory_is_valid(tmp_path: Path) -> None:
    catalog = load_content_catalog(write_content(tmp_path / "c", locations=[LOCATION]))
    assert catalog.cases == {}


def test_case_with_unknown_initial_information_is_rejected(tmp_path: Path) -> None:
    broken = dict(
        CASE,
        initial_evidence=[{"information_key": "missing_information"}],
    )
    with pytest.raises(ContentError, match="case .* references unknown information"):
        load_content_catalog(
            write_content(
                tmp_path / "c",
                locations=[LOCATION],
                information=[INFORMATION],
                cases=[broken],
            )
        )


def test_duplicate_case_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="duplicate case key"):
        load_content_catalog(
            write_content(
                tmp_path / "c",
                locations=[LOCATION],
                information=[INFORMATION],
                cases=[CASE, dict(CASE, question="Duplicate")],
            )
        )


def test_loads_item_definitions_and_location_spawns(content_dir: Path) -> None:
    catalog = load_content_catalog(content_dir)

    assert set(catalog.items) == {"credits", "flashlight", "medkit"}
    assert catalog.item_definition("credits").stackable is True
    assert catalog.item_definition("credits").weight == 0
    assert catalog.item_definition("flashlight").stackable is False
    assert catalog.location("base").items == ("credits", "medkit")
    assert catalog.location("forest").items == ("medkit", "flashlight")
    assert catalog.location("old_station").items == ("flashlight", "credits")


def test_location_spawn_with_unknown_item_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="references unknown item"):
        load_content_catalog(
            write_content(
                tmp_path / "c",
                locations=[dict(LOCATION, items=["missing_item"])],
                items=[ITEM],
            )
        )


def test_unique_item_cannot_be_materialized_twice(tmp_path: Path) -> None:
    unique_item = dict(
        ITEM,
        key="key_a17",
        type="OTHER",
        stackable=False,
        unique=True,
    )
    with pytest.raises(ContentError, match="unique item .* materialized more than once"):
        load_content_catalog(
            write_content(
                tmp_path / "c",
                locations=[dict(LOCATION, items=["key_a17", "key_a17"])],
                items=[unique_item],
            )
        )


def test_duplicate_item_definition_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="duplicate item key"):
        load_content_catalog(
            write_content(
                tmp_path / "c",
                locations=[LOCATION],
                items=[ITEM, dict(ITEM, name="Дубликат")],
            )
        )


def test_unique_item_definition_cannot_be_stackable(tmp_path: Path) -> None:
    broken = dict(ITEM, key="unique_key", stackable=True, unique=True)
    with pytest.raises(ContentError, match="unique items cannot be stackable"):
        load_content_catalog(
            write_content(tmp_path / "c", locations=[LOCATION], items=[broken])
        )


@pytest.mark.parametrize(
    ("raw_date", "expected"),
    [
        ("2024-03-15", date(2024, 3, 15)),
        ("not-a-date", None),
        (None, None),
    ],
)
def test_document_date_is_optional_and_lenient(
    tmp_path: Path, raw_date: str | None, expected: date | None
) -> None:
    information = dict(INFORMATION)
    if raw_date is not None:
        information["document_date"] = raw_date
    catalog = load_content_catalog(
        write_content(tmp_path / "content", locations=[LOCATION], information=[information])
    )
    assert catalog.information_definition("clue").document_date == expected


def test_conflicting_document_dates_are_preserved(tmp_path: Path) -> None:
    first = dict(INFORMATION, document_date="2024-03-15")
    second = dict(INFORMATION, key="other_clue", document_date="2024-03-16")
    catalog = load_content_catalog(
        write_content(tmp_path / "content", locations=[LOCATION], information=[first, second])
    )
    assert catalog.information_definition("clue").document_date == date(2024, 3, 15)
    assert catalog.information_definition("other_clue").document_date == date(2024, 3, 16)


def test_connection_to_unknown_location_is_rejected(tmp_path: Path) -> None:
    broken = dict(LOCATION, connections=["nowhere"])
    with pytest.raises(ContentError, match="unknown location"):
        load_content_catalog(write_content(tmp_path / "c", locations=[broken]))


def test_information_in_unknown_location_is_rejected(tmp_path: Path) -> None:
    broken = dict(INFORMATION, location_key="nowhere")
    with pytest.raises(ContentError, match="unknown location"):
        load_content_catalog(
            write_content(tmp_path / "c", locations=[LOCATION], information=[broken])
        )


def test_duplicate_location_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="duplicate location key"):
        load_content_catalog(
            write_content(tmp_path / "c", locations=[LOCATION, dict(LOCATION, name="Дубль")])
        )


def test_missing_field_is_rejected(tmp_path: Path) -> None:
    broken = {key: value for key, value in LOCATION.items() if key != "name"}
    with pytest.raises(ContentError, match="must define non-empty string field 'name'"):
        load_content_catalog(write_content(tmp_path / "c", locations=[broken]))


def test_invalid_json_is_rejected(tmp_path: Path) -> None:
    root = write_content(tmp_path / "c", locations=[LOCATION])
    (root / "locations" / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ContentError, match="invalid JSON"):
        load_content_catalog(root)


def test_unknown_start_location_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="start_location"):
        load_content_catalog(
            write_content(
                tmp_path / "c",
                manifest={"version": "v1", "start_location": "nowhere"},
                locations=[LOCATION],
            )
        )


def test_loads_npcs_from_repository_content(content_dir: Path) -> None:
    catalog = load_content_catalog(content_dir)
    assert sorted(catalog.npcs) == ["caretaker", "mechanic", "scout"]
    assert catalog.npc_definition("caretaker").initial_location == "base"
    assert catalog.npc_definition("caretaker").goals
    assert catalog.npc_definition("mechanic").initial_location == "old_station"


def test_loads_factions_from_repository_content(content_dir: Path) -> None:
    catalog = load_content_catalog(content_dir)

    assert sorted(catalog.factions) == ["council", "expedition", "union"]
    expedition = catalog.faction_definition("expedition")
    assert expedition.faction_type == "SCIENTIFIC"
    assert expedition.locations == ("base", "forest")
    assert expedition.hidden_goal
    assert catalog.faction_definition("council").hidden_goal is None


def test_content_without_factions_directory_is_valid(tmp_path: Path) -> None:
    catalog = load_content_catalog(write_content(tmp_path / "c", locations=[LOCATION]))
    assert catalog.factions == {}


def test_faction_with_unknown_location_is_rejected(tmp_path: Path) -> None:
    broken = dict(FACTION, locations=["nowhere"])
    with pytest.raises(ContentError, match="faction .* references unknown location"):
        load_content_catalog(
            write_content(tmp_path / "c", locations=[LOCATION], factions=[broken])
        )


def test_duplicate_faction_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="duplicate faction key"):
        load_content_catalog(
            write_content(
                tmp_path / "c",
                locations=[LOCATION],
                factions=[FACTION, dict(FACTION, name="Дубликат")],
            )
        )


def test_content_without_npcs_directory_is_valid(tmp_path: Path) -> None:
    catalog = load_content_catalog(write_content(tmp_path / "c", locations=[LOCATION]))
    assert catalog.npcs == {}


def test_npc_with_unknown_initial_location_is_rejected(tmp_path: Path) -> None:
    broken = dict(NPC, initial_location="nowhere")
    with pytest.raises(ContentError, match="starts in unknown location"):
        load_content_catalog(
            write_content(tmp_path / "c", locations=[LOCATION], npcs=[broken])
        )


def test_duplicate_npc_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ContentError, match="duplicate npc key"):
        load_content_catalog(
            write_content(
                tmp_path / "c",
                locations=[LOCATION],
                npcs=[NPC, dict(NPC, name="Дубль")],
            )
        )
