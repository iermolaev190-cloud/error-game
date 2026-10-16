"""Immutable item definitions and instance-scoped item state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    ItemId,
    LocationKey,
    WorldInstanceId,
)


class ItemType(StrEnum):
    CONSUMABLE = "CONSUMABLE"
    TOOL = "TOOL"
    TOKEN = "TOKEN"
    DOCUMENT = "DOCUMENT"
    OTHER = "OTHER"


class ItemVisibility(StrEnum):
    PUBLIC = "PUBLIC"
    SECRET = "SECRET"


class ItemOwnerType(StrEnum):
    CHARACTER = "CHARACTER"
    LOCATION = "LOCATION"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class ItemDefinition:
    """Global immutable item template loaded from content/items/*.json."""

    key: str
    name: str
    description: str
    weight: int
    type: ItemType
    stackable: bool
    unique: bool
    visibility: ItemVisibility = ItemVisibility.PUBLIC

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.name.strip():
            raise ValueError("item key and name must not be empty")
        if type(self.weight) is not int or self.weight < 0:
            raise ValueError("item weight must be a non-negative integer")
        if type(self.stackable) is not bool or type(self.unique) is not bool:
            raise ValueError("item stackable and unique must be booleans")
        if self.unique and self.stackable:
            raise ValueError("unique items cannot be stackable")


@dataclass(slots=True)
class Item:
    """A finite item instance with exactly one instance-scoped ownership record."""

    id: ItemId
    world_instance_id: WorldInstanceId
    key: str
    owner_type: ItemOwnerType
    owner_id: str | None
    location_key: LocationKey | None
    quantity: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: ItemId,
        world_instance_id: WorldInstanceId,
        definition: ItemDefinition,
        owner_type: ItemOwnerType,
        owner_id: str | None,
        location_key: LocationKey | None,
        quantity: int,
        now: datetime,
    ) -> "Item":
        if type(quantity) is not int or quantity < 1:
            raise DomainError(ErrorCode.INVALID_ACTION, "item quantity must be a positive integer")
        if (definition.unique or not definition.stackable) and quantity != 1:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"item {definition.key} must have quantity 1",
            )
        cls._validate_owner(owner_type, owner_id, location_key)

        return cls(
            id=id,
            world_instance_id=world_instance_id,
            key=definition.key,
            owner_type=owner_type,
            owner_id=owner_id,
            location_key=location_key,
            quantity=quantity,
            created_at=now,
            updated_at=now,
        )

    def apply(self, event: Event, definition: ItemDefinition) -> None:
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(ErrorCode.NOT_ALLOWED, "item event belongs to another instance")
        if event.type not in {
            EventType.ITEM_TAKEN,
            EventType.ITEM_DROPPED,
            EventType.ITEM_TRANSFERRED,
        }:
            raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported item event: {event.type}")
        change = next(
            (
                item_change
                for item_change in event.payload.get("item_changes", ())
                if str(item_change.get("item_id")) == str(self.id)
            ),
            None,
        )
        if change is None or change.get("delete") is True:
            raise DomainError(ErrorCode.INVALID_ACTION, f"event does not update item {self.id}")
        if (
            change.get("from_quantity") != self.quantity
            or str(change.get("from_owner_type")) != self.owner_type.value
            or change.get("from_owner_id") != self.owner_id
            or change.get("from_location_key")
            != (None if self.location_key is None else str(self.location_key))
        ):
            raise DomainError(ErrorCode.CONFLICT, f"item {self.id} changed since event was prepared")

        try:
            from_owner_type = ItemOwnerType(str(change["from_owner_type"]))
            owner_type = ItemOwnerType(str(change["to_owner_type"]))
        except (KeyError, ValueError) as exc:
            raise DomainError(ErrorCode.INVALID_ACTION, "invalid item owner type") from exc
        owner_id = change.get("to_owner_id")
        raw_location_key = change.get("to_location_key")
        location_key = None if raw_location_key is None else LocationKey(str(raw_location_key))
        quantity = change.get("to_quantity")
        merged_into_existing = change.get("merged_into_existing") is True
        if event.type is EventType.ITEM_TAKEN:
            valid_merge = (
                merged_into_existing
                and from_owner_type is ItemOwnerType.CHARACTER
                and owner_type is ItemOwnerType.CHARACTER
                and change.get("from_owner_id") == owner_id == event.actor
                and change.get("from_location_key") is None
                and raw_location_key is None
            )
            partial_source = (
                from_owner_type in (ItemOwnerType.LOCATION, ItemOwnerType.NONE)
                and owner_type is from_owner_type
                and change.get("from_owner_id") == owner_id
                and change.get("from_location_key") == raw_location_key
                and event.payload.get("location_key") == raw_location_key
                and event.actor == event.payload.get("character_id")
                and type(quantity) is int
                and 0 < quantity < self.quantity
            )
            valid_transfer = (
                not merged_into_existing
                and from_owner_type in (ItemOwnerType.LOCATION, ItemOwnerType.NONE)
                and owner_type is ItemOwnerType.CHARACTER
                and event.actor == owner_id
            )
            if not (valid_merge or valid_transfer or partial_source):
                raise DomainError(ErrorCode.INVALID_ACTION, "invalid ITEM_TAKEN owner transition")
        elif event.type is EventType.ITEM_DROPPED:
            valid_merge = (
                merged_into_existing
                and from_owner_type is ItemOwnerType.LOCATION
                and owner_type is ItemOwnerType.LOCATION
                and change.get("from_owner_id") is None
                and owner_id is None
                and change.get("from_location_key") == raw_location_key
                and event.actor == event.payload.get("character_id")
            )
            partial_source = (
                from_owner_type is ItemOwnerType.CHARACTER
                and owner_type is ItemOwnerType.CHARACTER
                and change.get("from_owner_id") == owner_id == event.actor
                and change.get("from_location_key") is None
                and raw_location_key is None
                and type(quantity) is int
                and 0 < quantity < self.quantity
            )
            valid_transfer = (
                not merged_into_existing
                and from_owner_type is ItemOwnerType.CHARACTER
                and owner_type is ItemOwnerType.LOCATION
                and event.actor == change.get("from_owner_id")
            )
            if not (valid_merge or valid_transfer or partial_source):
                raise DomainError(ErrorCode.INVALID_ACTION, "invalid ITEM_DROPPED owner transition")
        elif (
            from_owner_type is not ItemOwnerType.CHARACTER
            or owner_type is not ItemOwnerType.CHARACTER
            or event.actor != event.payload.get("initiator_character_id")
            or change.get("from_owner_id")
            not in {
                event.payload.get("initiator_character_id"),
                event.payload.get("counterparty_character_id"),
            }
            or owner_id
            not in {
                event.payload.get("initiator_character_id"),
                event.payload.get("counterparty_character_id"),
            }
        ):
            raise DomainError(ErrorCode.INVALID_ACTION, "invalid ITEM_TRANSFERRED owner transition")
        if type(quantity) is not int or quantity < 1:
            raise DomainError(ErrorCode.INVALID_ACTION, "item quantity must be a positive integer")
        if (definition.unique or not definition.stackable) and quantity != 1:
            raise DomainError(ErrorCode.INVALID_ACTION, f"item {self.key} must have quantity 1")
        self._validate_owner(owner_type, owner_id, location_key)
        self.owner_type = owner_type
        self.owner_id = owner_id
        self.location_key = location_key
        self.quantity = quantity
        self.updated_at = event.executed_at or event.created_at

    @staticmethod
    def _validate_owner(
        owner_type: ItemOwnerType, owner_id: str | None, location_key: LocationKey | None
    ) -> None:
        if owner_type is ItemOwnerType.CHARACTER:
            if not owner_id or location_key is not None:
                raise DomainError(ErrorCode.INVALID_ACTION, "character-owned item needs only owner_id")
        elif owner_type is ItemOwnerType.LOCATION:
            if location_key is None or owner_id is not None:
                raise DomainError(
                    ErrorCode.INVALID_ACTION,
                    "location-owned item needs location_key and no owner_id",
                )
        elif owner_type is ItemOwnerType.NONE and owner_id is not None:
            raise DomainError(ErrorCode.INVALID_ACTION, "unowned item cannot have owner_id")