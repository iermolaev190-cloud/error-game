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

from world_error.domain.information.information import InformationDefinition
from world_error.domain.locations.location import LocationDefinition
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

    @classmethod
    def build(
        cls,
        *,
        version: str,
        start_location: LocationKey,
        locations: Mapping[LocationKey, LocationDefinition],
        information: Mapping[str, InformationDefinition],
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
        return cls(
            version=version,
            start_location=start_location,
            locations=dict(locations),
            information=dict(information),
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

    def is_connected(self, source: LocationKey, target: LocationKey) -> bool:
        definition = self.locations.get(source)
        if definition is None:
            return False
        return target in definition.connections
