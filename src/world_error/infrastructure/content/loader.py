"""Загрузка контента из файлов в ``ContentCatalog``.

Контент — данные, а не код (20_TECH_ARCHITECTURE_V1 §22). Ошибки контента —
разработческая проблема, поэтому поднимается ``ContentError``, а не игровой
``DomainError``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from world_error.domain.content.catalog import ContentCatalog, ContentError
from world_error.domain.consequences.consequence import ConsequenceTrigger
from world_error.domain.consequences.rules import ConsequenceRule
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceType,
    ConsequenceVisibility,
    TriggerKind,
)
from world_error.domain.events.event import EventType
from world_error.domain.factions.faction import FactionDefinition
from world_error.domain.investigations.case import (
    CaseDefinition,
    CaseEvidenceRelevance,
    CaseTheoryConfidence,
    InitialEvidenceDefinition,
    ResolutionCriteria,
)
from world_error.domain.information.information import InformationDefinition
from world_error.domain.items.item import ItemDefinition, ItemType, ItemVisibility
from world_error.domain.locations.location import LocationDefinition
from world_error.domain.npcs.npc import NpcDefinition
from world_error.domain.shared.kernel import DomainError, LocationKey

MANIFEST_FILE = "manifest.json"
LOCATIONS_DIR = "locations"
INFORMATION_DIR = "information"
ITEMS_DIR = "items"
NPCS_DIR = "npcs"
FACTIONS_DIR = "factions"
CASES_DIR = "cases"
CONSEQUENCES_DIR = "consequences"


def load_content_catalog(content_dir: Path | str) -> ContentCatalog:
    root = Path(content_dir)
    manifest_path = root / MANIFEST_FILE
    manifest = _read_object(manifest_path)

    locations = _load_locations(root / LOCATIONS_DIR)
    information = _load_information(root / INFORMATION_DIR)
    items = _load_items(root / ITEMS_DIR)
    npcs = _load_npcs(root / NPCS_DIR)
    factions = _load_factions(root / FACTIONS_DIR)
    cases = _load_cases(root / CASES_DIR)
    rules = _load_consequences(root / CONSEQUENCES_DIR)

    return ContentCatalog.build(
        version=_require_str(manifest, "version", manifest_path),
        start_location=LocationKey(_require_str(manifest, "start_location", manifest_path)),
        locations=locations,
        information=information,
        items=items,
        npcs=npcs,
        factions=factions,
        cases=cases,
        rules=rules,
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
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            raise ContentError(f"content file {path} field 'items' must be a list")
        item_keys = tuple(
            _require_string_value(item, "location item key", path) for item in raw_items
        )
        locations[key] = LocationDefinition(
            key=key,
            name=_require_str(data, "name", path),
            type=_require_str(data, "type", path),
            description=_require_str(data, "description", path),
            connections=connections,
            items=item_keys,
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
        external_url = data.get("external_url")
        if external_url is not None and not isinstance(external_url, str):
            raise ContentError(
                f"content file {path} field 'external_url' must be a string"
            )
        items[key] = InformationDefinition(
            key=key,
            location_key=LocationKey(_require_str(data, "location_key", path)),
            information_type=_require_str(data, "type", path),
            source=_require_str(data, "source", path),
            authenticity=_require_str(data, "authenticity", path),
            access=_require_str(data, "access", path),
            content=_require_str(data, "content", path),
            truth=_require_str(data, "truth", path),
            document_date=_optional_date(data.get("document_date")),
            external_url=external_url if external_url and external_url.strip() else None,
        )
    return items


def _load_items(directory: Path) -> dict[str, ItemDefinition]:
    """Load immutable item definitions; an empty or absent catalog is valid."""
    items: dict[str, ItemDefinition] = {}
    if not directory.is_dir():
        return items
    for path in _json_files(directory, require_any=False):
        data = _read_object(path)
        key = _require_str(data, "key", path)
        if key in items:
            raise ContentError(f"duplicate item key {key!r} ({path})")
        try:
            items[key] = ItemDefinition(
                key=key,
                name=_require_str(data, "name", path),
                description=_require_str(data, "description", path),
                weight=_require_int(data, "weight", path),
                type=ItemType(_require_str(data, "type", path)),
                stackable=_require_bool(data, "stackable", path),
                unique=_require_bool(data, "unique", path),
                visibility=ItemVisibility(data.get("visibility", ItemVisibility.PUBLIC.value)),
            )
        except (TypeError, ValueError) as exc:
            raise ContentError(f"invalid item definition {key!r}: {exc} ({path})") from exc
    return items


def _optional_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


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


def _load_factions(directory: Path) -> dict[str, FactionDefinition]:
    """Faction definitions are immutable global content, not instance state."""
    items: dict[str, FactionDefinition] = {}
    if not directory.is_dir():
        return items
    for path in _json_files(directory, require_any=False):
        data = _read_object(path)
        key = _require_str(data, "key", path)
        if key in items:
            raise ContentError(f"duplicate faction key {key!r} ({path})")
        hidden_goal = data.get("hidden_goal")
        if hidden_goal is not None and not isinstance(hidden_goal, str):
            raise ContentError(f"content file {path} field 'hidden_goal' must be a string")
        items[key] = FactionDefinition(
            key=key,
            name=_require_str(data, "name", path),
            description=_require_str(data, "description", path),
            faction_type=_require_str(data, "type", path),
            public_goal=_require_str(data, "public_goal", path),
            locations=tuple(
                LocationKey(str(location_key))
                for location_key in _require_list(data, "locations", path)
            ),
            hidden_goal=hidden_goal,
        )
    return items


def _load_cases(directory: Path) -> dict[str, CaseDefinition]:
    """Load authored investigation definitions; per-instance Case is seeded later."""
    items: dict[str, CaseDefinition] = {}
    if not directory.is_dir():
        return items
    for path in _json_files(directory, require_any=False):
        data = _read_object(path)
        key = _require_str(data, "key", path)
        if key in items:
            raise ContentError(f"duplicate case key {key!r} ({path})")
        raw_evidence = _require_list(data, "initial_evidence", path)
        initial_evidence: list[InitialEvidenceDefinition] = []
        try:
            for raw_link in raw_evidence:
                if not isinstance(raw_link, dict):
                    raise ContentError(f"case {key!r} initial_evidence entries must be objects")
                initial_evidence.append(
                    InitialEvidenceDefinition(
                        information_key=_require_str(raw_link, "information_key", path),
                        relevance=CaseEvidenceRelevance(
                            raw_link.get("relevance", CaseEvidenceRelevance.UNKNOWN.value)
                        ),
                    )
                )
            criteria_data = data.get("resolution_criteria", {})
            if not isinstance(criteria_data, dict):
                raise ContentError(f"case {key!r} resolution_criteria must be an object")
            min_confidence_value = criteria_data.get("required_theory_min_confidence")
            criteria = ResolutionCriteria(
                required_evidence_count=_optional_int(criteria_data, "required_evidence_count", path),
                required_theory_count=_optional_int(criteria_data, "required_theory_count", path),
                required_theory_min_confidence=(
                    None
                    if min_confidence_value is None
                    else CaseTheoryConfidence(str(min_confidence_value))
                ),
                required_distinct_contributors=_optional_int(
                    criteria_data, "required_distinct_contributors", path
                ),
                required_actions=tuple(
                    _require_string_value(action, "required action", path)
                    for action in _require_list(criteria_data, "required_actions", path)
                ) if "required_actions" in criteria_data else (),
            )
            items[key] = CaseDefinition(
                key=key,
                question=_require_str(data, "question", path),
                opening_hint=_require_str(data, "opening_hint", path),
                initial_evidence=tuple(initial_evidence),
                resolution_criteria=criteria,
            )
        except (TypeError, ValueError, DomainError) as exc:
            raise ContentError(f"invalid case definition {key!r}: {exc} ({path})") from exc
    return items


def _load_consequences(directory: Path) -> dict[str, ConsequenceRule]:
    """Правила последствий. Каталог может отсутствовать: мир без правил допустим."""
    items: dict[str, ConsequenceRule] = {}
    if not directory.is_dir():
        return items
    for path in _json_files(directory, require_any=False):
        data = _read_object(path)
        key = _require_str(data, "key", path)
        if key in items:
            raise ContentError(f"duplicate consequence rule key {key!r} ({path})")
        try:
            items[key] = _build_rule(key, data)
        except ContentError as exc:
            raise ContentError(f"{exc} ({path})") from exc
    return items


def _build_rule(key: str, data: dict[str, Any]) -> ConsequenceRule:
    try:
        trigger_data = dict(data["trigger"])
        trigger_kind = TriggerKind(str(trigger_data["kind"]))
        if trigger_kind is TriggerKind.AFTER_TICKS:
            trigger = ConsequenceTrigger.after_ticks(int(trigger_data["delay_ticks"]))
        elif trigger_kind is TriggerKind.ON_EVENT_TYPE:
            trigger = ConsequenceTrigger.on_event_type(str(trigger_data["event_type"]))
        else:
            trigger = ConsequenceTrigger.immediate()

        effect_data = dict(data["effect"])
        effect = ConsequenceEffect(str(effect_data.pop("kind")))
        return ConsequenceRule(
            key=key,
            on_event_type=EventType(str(data["on_event_type"])),
            when_payload={str(k): str(v) for k, v in dict(data["when_payload"]).items()},
            type=ConsequenceType(str(data["type"])),
            scale=ConsequenceScale(str(data["scale"])),
            visibility=ConsequenceVisibility(str(data["visibility"])),
            trigger=trigger,
            effect=effect,
            effect_keys=effect_data,
        )
    except (KeyError, TypeError, ValueError, DomainError) as exc:
        raise ContentError(f"invalid consequence rule {key!r}: {exc}") from exc


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


def _require_string_value(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContentError(f"content file {path} field {field!r} must be a non-empty string")
    return value


def _require_int(data: dict[str, Any], field: str, path: Path) -> int:
    value = data.get(field)
    if type(value) is not int:
        raise ContentError(f"content file {path} field {field!r} must be an integer")
    return value


def _optional_int(data: dict[str, Any], field: str, path: Path) -> int:
    if field not in data:
        return 0
    return _require_int(data, field, path)


def _require_bool(data: dict[str, Any], field: str, path: Path) -> bool:
    value = data.get(field)
    if type(value) is not bool:
        raise ContentError(f"content file {path} field {field!r} must be a boolean")
    return value
