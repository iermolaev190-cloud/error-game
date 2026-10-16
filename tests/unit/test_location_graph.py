"""Unit: граф локаций берётся из контента, а не из кода."""

from __future__ import annotations

import pytest

from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.shared.kernel import DomainError, ErrorCode, LocationKey

BASE = LocationKey("base")
FOREST = LocationKey("forest")
OLD_STATION = LocationKey("old_station")


def test_catalog_contains_three_locations(catalog: ContentCatalog) -> None:
    assert set(catalog.locations) == {BASE, FOREST, OLD_STATION}
    assert catalog.start_location == BASE
    assert catalog.version == "v1"


def test_expected_connections_exist(catalog: ContentCatalog) -> None:
    assert catalog.is_connected(BASE, FOREST)
    assert catalog.is_connected(FOREST, BASE)
    assert catalog.is_connected(FOREST, OLD_STATION)
    assert catalog.is_connected(OLD_STATION, FOREST)


def test_direct_route_base_to_old_station_does_not_exist(catalog: ContentCatalog) -> None:
    assert not catalog.is_connected(BASE, OLD_STATION)
    assert not catalog.is_connected(OLD_STATION, BASE)


def test_unknown_location_is_not_found(catalog: ContentCatalog) -> None:
    with pytest.raises(DomainError) as exc_info:
        catalog.location(LocationKey("nowhere"))
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_information_is_placed_in_old_station(catalog: ContentCatalog) -> None:
    definition = catalog.information_definition("damaged_radio")
    assert definition.location_key == OLD_STATION
    assert definition.content
    assert definition.truth
    assert definition.content != definition.truth
