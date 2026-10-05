"""Unit: item definitions, finite quantities, and ownership shape."""

from datetime import datetime, timezone

import pytest

from world_error.domain.events.event import Event, EventType
from world_error.domain.items.item import (
    Item,
    ItemDefinition,
    ItemOwnerType,
    ItemType,
    ItemVisibility,
)
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    EventId,
    ItemId,
    LocationKey,
    WorldInstanceId,
    new_item_id,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")


def test_new_item_id_uses_item_namespace() -> None:
    assert new_item_id().startswith("itm_")


def make_definition(
    *, stackable: bool = True, unique: bool = False, visibility: ItemVisibility = ItemVisibility.PUBLIC
) -> ItemDefinition:
    return ItemDefinition(
        key="medkit",
        name="Аптечка",
        description="Расходуемый медицинский набор.",
        weight=250,
        type=ItemType.CONSUMABLE,
        stackable=stackable,
        unique=unique,
        visibility=visibility,
    )


def make_item(
    *, quantity: int = 1, owner_type: ItemOwnerType = ItemOwnerType.NONE,
    owner_id: str | None = None, location_key: LocationKey | None = None,
    definition: ItemDefinition | None = None,
) -> Item:
    return Item.create(
        id=ItemId("itm_one"),
        world_instance_id=WORLD_ID,
        definition=definition or make_definition(),
        owner_type=owner_type,
        owner_id=owner_id,
        location_key=location_key,
        quantity=quantity,
        now=NOW,
    )


def test_item_definition_is_immutable_content_with_visibility_default() -> None:
    definition = make_definition()
    assert definition.visibility is ItemVisibility.PUBLIC
    assert definition.weight == 250


def test_unique_item_cannot_be_stackable() -> None:
    with pytest.raises(ValueError, match="unique items cannot be stackable"):
        make_definition(stackable=True, unique=True)


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True])
def test_item_requires_positive_integer_quantity(quantity: int) -> None:
    with pytest.raises(DomainError) as exc_info:
        make_item(quantity=quantity)
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_nonstackable_and_unique_items_require_quantity_one() -> None:
    nonstackable = make_definition(stackable=False)
    unique = ItemDefinition(
        key="key_a17",
        name="Ключ A17",
        description="Единственный ключ.",
        weight=20,
        type=ItemType.OTHER,
        stackable=False,
        unique=True,
    )
    for definition in (nonstackable, unique):
        with pytest.raises(DomainError) as exc_info:
            make_item(quantity=2, definition=definition)
        assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_owner_shape_is_validated_for_character_location_and_none() -> None:
    character_item = make_item(owner_type=ItemOwnerType.CHARACTER, owner_id="ch_anna")
    location = LocationKey("base")
    location_item = make_item(
        owner_type=ItemOwnerType.LOCATION,
        location_key=location,
    )
    unowned_at_location = make_item(location_key=location)

    assert character_item.owner_id == "ch_anna"
    assert location_item.owner_id is None
    assert location_item.location_key == location
    assert unowned_at_location.owner_type is ItemOwnerType.NONE


def test_item_definition_has_no_npc_owner_type() -> None:
    assert {owner.value for owner in ItemOwnerType} == {"CHARACTER", "LOCATION", "NONE"}


def test_partial_take_event_keeps_remainder_at_location() -> None:
    definition = make_definition()
    item = make_item(
        quantity=5,
        owner_type=ItemOwnerType.LOCATION,
        location_key=LocationKey("base"),
        definition=definition,
    )
    event = Event(
        id=EventId("ev_take_partial"),
        world_instance_id=WORLD_ID,
        type=EventType.ITEM_TAKEN,
        created_at=NOW,
        executed_at=NOW,
        actor="ch_anna",
        payload={
            "character_id": "ch_anna",
            "location_key": "base",
            "item_changes": [
                {
                    "item_id": "itm_one",
                    "from_quantity": 5,
                    "from_owner_type": "LOCATION",
                    "from_owner_id": None,
                    "from_location_key": "base",
                    "to_quantity": 2,
                    "to_owner_type": "LOCATION",
                    "to_owner_id": None,
                    "to_location_key": "base",
                    "merged_into_existing": False,
                    "delete": False,
                }
            ],
        },
    )

    item.apply(event, definition)

    assert item.quantity == 2
    assert item.owner_type is ItemOwnerType.LOCATION
    assert item.location_key == LocationKey("base")