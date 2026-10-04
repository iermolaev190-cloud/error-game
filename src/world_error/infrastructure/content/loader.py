"""Загрузка контента из файлов в ``ContentCatalog``.

Контент — данные, а не код (20_TECH_ARCHITECTURE_V1 §22). Ошибки контента —
разработческая проблема, поэтому поднимается ``ContentError``, а не игровой
``DomainError``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from world_error.domain.content.catalog import ContentCatalog, ContentError
from world_error.domain.information.information import InformationDefinition
from world_error.domain.locations.location import LocationDefinition
from world_error.domain.npcs.npc import NpcDefinition
from world_error.domain.shared.kernel import LocationKey

MANIFEST_FILE = "manifest.json"
LOCATIONS_DIR = "locations"
INFORMATION_DIR = "information"
NPCS_DIR = "npcs"


def load_content_catalog(content_dir: Path | str) -> ContentCatalog:
    root = Path(content_dir)
    manifest_path = root / MANIFEST_FILE
    manifest = _read_object(manifest_path)

    locations = _load_locations(root / LOCATIONS_DIR)
    information = _load_information(root / INFORMATION_DIR)
    npcs = _load_npcs(root / NPCS_DIR)

    return ContentCatalog.build(
        version=_require_str(manifest, "version", manifest_path),
        start_location=LocationKey(_require_str(manifest, "start_location", manifest_path)),
        locations=locations,
        information=information,
        npcs=npcs,
    )


def _load_locations(directory: Path) -> dict[LocationKey, LocationDefinition]:
    locations: dict[LocationKey, LocationDefinition] = {}
    for path in _json_files(directory):
        data = _read_object(path)
        key = LocationKey(_require_str(data, "key", path))
        if key in locations:
            raise ContentError(f"duplicate location key {key!r} ({path})")
        connections = frozenset(
            LocationKey(str(item)) for item in _require_list(data, "connections", path)
        )
        locations[key] = LocationDefinition(
            key=key,
            name=_require_str(data, "name", path),
            type=_require_str(data, "type", path),
            description=_require_str(data, "description", path),
            connections=connections,
        )
    return locations


def _load_information(directory: Path) -> dict[str, InformationDefinition]:
    items: dict[str, InformationDefinition] = {}
    # Мир без информационных объектов — допустимое состояние, поэтому пустой
    # каталог здесь не ошибка (в отличие от локаций).
    for path in _json_files(directory, require_any=False):
        data = _read_object(path)
        key = _require_str(data, "key", path)
        if key in items:
            raise ContentError(f"duplicate information key {key!r} ({path})")
        items[key] = InformationDefinition(
            key=key,
            location_key=LocationKey(_require_str(data, "location_key", path)),
            information_type=_require_str(data, "type", path),
            source=_require_str(data, "source", path),
            authenticity=_require_str(data, "authenticity", path),
            access=_require_str(data, "access", path),
            content=_require_str(data, "content", path),
            truth=_require_str(data, "truth", path),
        )
    return items


def _load_npcs(directory: Path) -> dict[str, NpcDefinition]:
    """Загрузка NPC. Каталог может отсутствовать: мир без NPC допустим."""
    items: dict[str, NpcDefinition] = {}
    if not directory.is_dir():
        return items
    for path in _json_files(directory, require_any=False):
        data = _read_object(path)
        key = _require_str(data, "key", path)
        if key in items:
            raise ContentError(f"duplicate npc key {key!r} ({path})")
        items[key] = NpcDefinition(
            key=key,
            name=_require_str(data, "name", path),
            description=_require_str(data, "description", path),
            initial_location=LocationKey(_require_str(data, "initial_location", path)),
            goals=tuple(str(goal) for goal in _require_list(data, "goals", path)),
        )
    return items


def _json_files(directory: Path, *, require_any: bool = True) -> list[Path]:
    if not directory.is_dir():
        raise ContentError(f"content directory not found: {directory}")
    files = sorted(directory.glob("*.json"))
    if require_any and not files:
        raise ContentError(f"content directory has no *.json files: {directory}")
    return files


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ContentError(f"content file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContentError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ContentError(f"content file must contain a JSON object: {path}")
    return data


def _require_str(data: dict[str, Any], field: str, path: Path) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContentError(f"content file {path} must define non-empty string field {field!r}")
    return value


def _require_list(data: dict[str, Any], field: str, path: Path) -> list[Any]:
    value = data.get(field)
    if not isinstance(value, list):
        raise ContentError(f"content file {path} must define list field {field!r}")
    return value
