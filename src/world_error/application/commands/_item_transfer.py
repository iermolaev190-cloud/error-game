"""Shared planning and atomic persistence for item ownership transfers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable, Iterable

from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event
from world_error.domain.items.item import Item, ItemOwnerType
from world_error.domain.shared.kernel import DomainError, ErrorCode, ItemId, LocationKey, WorldInstanceId


@dataclass(frozen=True, slots=True)
class ItemTransferReceipt:
    source_item_id: ItemId
    destination_item_id: ItemId
    quantity: int
    merged_into_existing: bool


class ItemTransferWorkspace:
    """Stages all item changes before committing one event/UoW."""

    def __init__(
        self,
        *,
        catalog: ContentCatalog,
        now: datetime,
        new_item_id: Callable[[], ItemId],
        existing_items: Iterable[Item],
    ) -> None:
        self._catalog = catalog
        self._now = now
        self._new_item_id = new_item_id
        self._originals = {item.id: item for item in existing_items}
        self._states = {item.id: replace(item) for item in self._originals.values()}
        self._created: dict[ItemId, Item] = {}
        self._deleted: set[ItemId] = set()
        self._merged: set[ItemId] = set()
        self._receipts: list[ItemTransferReceipt] = []

    def transfer(
        self,
        *,
        item_id: ItemId,
        quantity: int,
        owner_type: ItemOwnerType,
        owner_id: str | None,
        location_key: LocationKey | None,
        excluded_target_ids: frozenset[ItemId] = frozenset(),
    ) -> ItemTransferReceipt:
        source = self._states.get(item_id)
        if source is None or item_id in self._deleted:
            raise DomainError(ErrorCode.NOT_FOUND, f"item not found: {item_id}")
        definition = self._catalog.item_definition(source.key)
        if type(quantity) is not int or quantity < 1 or quantity > source.quantity:
            raise DomainError(ErrorCode.INVALID_ACTION, "transfer quantity is outside item quantity")
        if (definition.unique or not definition.stackable) and quantity != source.quantity:
            raise DomainError(ErrorCode.INVALID_ACTION, f"item {source.key} cannot be split")

        target = None
        if definition.stackable:
            target = next(
                (
                    item
                    for candidate_id, item in self._states.items()
                    if candidate_id != item_id
                    and candidate_id not in self._deleted
                    and candidate_id not in excluded_target_ids
                    and item.key == source.key
                    and item.owner_type is owner_type
                    and item.owner_id == owner_id
                    and item.location_key == location_key
                ),
                None,
            )

        if target is not None:
            target.quantity += quantity
            target.updated_at = self._now
            self._merged.add(target.id)
            remaining = source.quantity - quantity
            if remaining:
                source.quantity = remaining
                source.updated_at = self._now
            else:
                self._deleted.add(source.id)
            destination_id = target.id
            merged = True
        elif quantity == source.quantity:
            source.owner_type = owner_type
            source.owner_id = owner_id
            source.location_key = location_key
            source.updated_at = self._now
            destination_id = source.id
            merged = False
        else:
            source.quantity -= quantity
            source.updated_at = self._now
            definition = self._catalog.item_definition(source.key)
            created = Item.create(
                id=self._new_item_id(),
                world_instance_id=source.world_instance_id,
                definition=definition,
                owner_type=owner_type,
                owner_id=owner_id,
                location_key=location_key,
                quantity=quantity,
                now=self._now,
            )
            self._created[created.id] = created
            destination_id = created.id
            merged = False

        receipt = ItemTransferReceipt(item_id, destination_id, quantity, merged)
        self._receipts.append(receipt)
        return receipt

    def event_payload(self) -> dict[str, object]:
        changes: list[dict[str, object]] = []
        for item_id, original in self._originals.items():
            state = self._states[item_id]
            if item_id in self._deleted:
                changes.append(self._change_record(original, original, delete=True))
            elif _state_tuple(original) != _state_tuple(state):
                changes.append(
                    self._change_record(
                        original, state, merged_into_existing=item_id in self._merged
                    )
                )
        return {
            "item_changes": changes,
            "created_items": [_item_record(item) for item in self._created.values()],
            "transfers": [
                {
                    "source_item_id": str(receipt.source_item_id),
                    "destination_item_id": str(receipt.destination_item_id),
                    "quantity": receipt.quantity,
                    "merged_into_existing": receipt.merged_into_existing,
                }
                for receipt in self._receipts
            ],
        }

    def persist(self, *, uow, instance, expected_state_version: int, event: Event) -> None:  # noqa: ANN001
        instance.register_applied_event(event)
        for item_id, original in self._originals.items():
            if item_id in self._deleted:
                uow.items.delete(original)
                continue
            state = self._states[item_id]
            if _state_tuple(original) == _state_tuple(state):
                continue
            original.apply(event, self._catalog.item_definition(original.key))
            uow.items.save(original)
        for item in self._created.values():
            uow.items.add(item)
        uow.world_instances.save(
            instance, expected_state_version=expected_state_version
        )
        uow.events.append(event)
        uow.commit()

    @staticmethod
    def _change_record(
        original: Item,
        state: Item,
        *,
        merged_into_existing: bool = False,
        delete: bool = False,
    ) -> dict[str, object]:
        return {
            "item_id": str(original.id),
            "from_quantity": original.quantity,
            "from_owner_type": original.owner_type.value,
            "from_owner_id": original.owner_id,
            "from_location_key": (
                None if original.location_key is None else str(original.location_key)
            ),
            "to_quantity": state.quantity,
            "to_owner_type": state.owner_type.value,
            "to_owner_id": state.owner_id,
            "to_location_key": None if state.location_key is None else str(state.location_key),
            "merged_into_existing": merged_into_existing,
            "delete": delete,
        }


def _state_tuple(item: Item) -> tuple[object, ...]:
    return (item.owner_type, item.owner_id, item.location_key, item.quantity)


def _item_record(item: Item) -> dict[str, object]:
    return {
        "item_id": str(item.id),
        "world_instance_id": str(item.world_instance_id),
        "key": item.key,
        "owner_type": item.owner_type.value,
        "owner_id": item.owner_id,
        "location_key": None if item.location_key is None else str(item.location_key),
        "quantity": item.quantity,
    }