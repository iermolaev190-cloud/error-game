"""Каталог контента — глобальные неизменяемые определения.

Контент и состояние разделены (20_TECH_ARCHITECTURE_V1 §22): движок знает, как
работает мир, но не знает, кто конкретно повредил радио. Поэтому описания живут
в ``content/``, а в БД хранится только instance-специфичное состояние.

Каталог immutable и общий для всех WORLD INSTANCE: данные инстансов не
смешиваются, потому что каталог не содержит состояния.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from world_error.domain.consequences.rules import ConsequenceRule
from world_error.domain.consequences.vocabulary import ConsequenceEffect
from world_error.domain.factions.faction import FactionDefinition
from world_error.domain.investigations.case import CaseDefinition
from world_error.domain.information.information import InformationDefinition
from world_error.domain.items.item import ItemDefinition
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.locations.location import LocationDefinition
from world_error.domain.npcs.npc import NpcDefinition
from world_error.domain.shared.kernel import DomainError, ErrorCode, LocationKey


class ContentError(Exception):
    """Ошибка контента: разработческая/системная, а не игровая.

    Игровая ошибка ≠ системная ошибка (20_TECH_ARCHITECTURE_V1 §32).
    """


@dataclass(frozen=True, slots=True)
class ContentCatalog:
    version: str
    start_location: LocationKey
    locations: Mapping[LocationKey, LocationDefinition]
    information: Mapping[str, InformationDefinition]
    items: Mapping[str, ItemDefinition]
    npcs: Mapping[str, NpcDefinition]
    factions: Mapping[str, FactionDefinition]
    cases: Mapping[str, CaseDefinition]
    rules: Mapping[str, ConsequenceRule]

    @classmethod
    def build(
        cls,
        *,
        version: str,
        start_location: LocationKey,
        locations: Mapping[LocationKey, LocationDefinition],
        information: Mapping[str, InformationDefinition],
        items: Mapping[str, ItemDefinition] | None = None,
        npcs: Mapping[str, NpcDefinition] | None = None,
        factions: Mapping[str, FactionDefinition] | None = None,
        cases: Mapping[str, CaseDefinition] | None = None,
        rules: Mapping[str, ConsequenceRule] | None = None,
    ) -> "ContentCatalog":
        if not locations:
            raise ContentError("content has no locations")
        if start_location not in locations:
            raise ContentError(f"start_location {start_location!r} is not defined in content")
        for definition in locations.values():
            for target in definition.connections:
                if target == definition.key:
                    raise ContentError(f"location {definition.key!r} is connected to itself")
                if target not in locations:
                    raise ContentError(
                        f"location {definition.key!r} is connected to unknown location {target!r}"
                    )
        for information_definition in information.values():
            if information_definition.location_key not in locations:
                raise ContentError(
                    f"information {information_definition.key!r} is placed in unknown location "
                    f"{information_definition.location_key!r}"
                )
        item_definitions = dict(items or {})
        unique_spawns: set[str] = set()
        for location in locations.values():
            for item_key in location.items:
                item_definition = item_definitions.get(item_key)
                if item_definition is None:
                    raise ContentError(
                        f"location {location.key!r} references unknown item {item_key!r}"
                    )
                if item_definition.unique:
                    if item_key in unique_spawns:
                        raise ContentError(
                            f"unique item {item_key!r} is materialized more than once"
                        )
                    unique_spawns.add(item_key)
        npc_definitions = dict(npcs or {})
        for npc_definition in npc_definitions.values():
            if npc_definition.initial_location not in locations:
                raise ContentError(
                    f"npc {npc_definition.key!r} starts in unknown location "
                    f"{npc_definition.initial_location!r}"
                )
        faction_definitions = dict(factions or {})
        for faction_definition in faction_definitions.values():
            for location_key in faction_definition.locations:
                if location_key not in locations:
                    raise ContentError(
                        f"faction {faction_definition.key!r} references unknown location "
                        f"{location_key!r}"
                    )
        case_definitions = dict(cases or {})
        for case_definition in case_definitions.values():
            for evidence in case_definition.initial_evidence:
                if evidence.information_key not in information:
                    raise ContentError(
                        f"case {case_definition.key!r} references unknown information "
                        f"{evidence.information_key!r}"
                    )
        rule_items = dict(rules or {})
        for rule in rule_items.values():
            _validate_rule(rule, npc_definitions, information, locations)
        return cls(
            version=version,
            start_location=start_location,
            locations=dict(locations),
            information=dict(information),
            items=item_definitions,
            npcs=npc_definitions,
            factions=faction_definitions,
            cases=case_definitions,
            rules=rule_items,
        )

    def has_location(self, key: LocationKey) -> bool:
        return key in self.locations

    def location(self, key: LocationKey) -> LocationDefinition:
        try:
            return self.locations[key]
        except KeyError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown location: {key}") from exc

    def information_definition(self, key: str) -> InformationDefinition:
        try:
            return self.information[key]
        except KeyError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown information: {key}") from exc

    def item_definition(self, key: str) -> ItemDefinition:
        try:
            return self.items[key]
        except KeyError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown item: {key}") from exc

    def npc_definition(self, key: str) -> NpcDefinition:
        try:
            return self.npcs[key]
        except KeyError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown npc: {key}") from exc

    def faction_definition(self, key: str) -> FactionDefinition:
        try:
            return self.factions[key]
        except KeyError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown faction: {key}") from exc

    def case_definition(self, key: str) -> CaseDefinition:
        try:
            return self.cases[key]
        except KeyError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown case: {key}") from exc

    def is_connected(self, source: LocationKey, target: LocationKey) -> bool:
        definition = self.locations.get(source)
        if definition is None:
            return False
        return target in definition.connections

    def consequence_rule(self, key: str) -> ConsequenceRule:
        try:
            return self.rules[key]
        except KeyError as exc:
            raise DomainError(ErrorCode.NOT_FOUND, f"unknown consequence rule: {key}") from exc

    def rules_for_event_type(self, event_type) -> tuple[ConsequenceRule, ...]:  # noqa: ANN001
        return tuple(rule for rule in self.rules.values() if rule.on_event_type is event_type)


def _validate_rule(
    rule: ConsequenceRule,
    npcs: Mapping[str, NpcDefinition],
    information: Mapping[str, InformationDefinition],
    locations: Mapping[LocationKey, LocationDefinition],
) -> None:
    """Правило обязано ссылаться только на существующий контент."""
    keys = rule.effect_keys
    if rule.effect is ConsequenceEffect.INFORMATIONAL_LEARN:
        _require_content_key(npcs, str(keys["npc_key"]), "npc", rule)
        _require_content_key(information, str(keys["information_key"]), "information", rule)
        return
    if rule.effect in (
        ConsequenceEffect.PHYSICAL_STATUS_CHANGE,
        ConsequenceEffect.PHYSICAL_RELOCATE,
    ):
        _require_content_key(npcs, str(keys["npc_key"]), "npc", rule)
        if rule.effect is ConsequenceEffect.PHYSICAL_RELOCATE:
            _require_content_key(
                locations, LocationKey(str(keys["to_location_key"])), "location", rule
            )
        return
    if rule.effect is ConsequenceEffect.RELATIONAL_SHIFT:
        for prefix in ("holder", "subject"):
            if str(keys[f"{prefix}_type"]) != SubjectType.NPC.value:
                raise ContentError(
                    f"consequence rule {rule.key!r} can reference only NPC subjects: "
                    "characters have no content keys"
                )
            _require_content_key(npcs, str(keys[f"{prefix}_key"]), "npc", rule)


def _require_content_key(collection: Mapping, key, kind: str, rule: ConsequenceRule) -> None:  # noqa: ANN001
    if key not in collection:
        raise ContentError(
            f"consequence rule {rule.key!r} references unknown {kind}: {key!r}"
        )
