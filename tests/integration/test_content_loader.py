"""Integration: загрузка контента из файлов и её ошибки."""

from __future__ import annotations

import json
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


def write_content(
    root: Path,
    *,
    manifest: dict[str, Any] | None = None,
    locations: list[dict[str, Any]] | None = None,
    information: list[dict[str, Any]] | None = None,
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
    return root


def test_loads_repository_content(content_dir: Path) -> None:
    catalog = load_content_catalog(content_dir)
    assert catalog.version == "v1"
    assert set(catalog.locations) == {"base", "forest", "old_station"}
    assert set(catalog.information) == {"damaged_radio"}
    assert catalog.information_definition("damaged_radio").truth.endswith("инструментом.")


def test_loads_minimal_content(tmp_path: Path) -> None:
    catalog = load_content_catalog(
        write_content(tmp_path / "content", locations=[LOCATION], information=[INFORMATION])
    )
    assert catalog.start_location == "base"
    assert catalog.location("base").name == "Лагерь"
    assert catalog.information_definition("clue").content == "Корпус вскрыт."


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
