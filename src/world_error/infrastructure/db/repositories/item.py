"""Repository for instance-scoped item instances."""

from __future__ import annotations

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.items.item import Item, ItemOwnerType
from world_error.domain.shared.kernel import DomainError, ErrorCode, ItemId, LocationKey, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import item_from_row, item_row
from world_error.infrastructure.db.tables import items


class SqlItemRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: Item) -> None:
        self._session.execute(insert(items).values(**item_row(item)))

    def get(self, world_instance_id: WorldInstanceId, item_id: ItemId) -> Item:
        row = (
            self._session.execute(
                select(items).where(
                    items.c.world_instance_id == str(world_instance_id),
                    items.c.id == str(item_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"item not found: {item_id}")
        return item_from_row(dict(row))

    def list_by_owner(
        self,
        world_instance_id: WorldInstanceId,
        owner_type: ItemOwnerType,
        owner_id: str | None,
    ) -> list[Item]:
        stmt = (
            select(items)
            .where(
                items.c.world_instance_id == str(world_instance_id),
                items.c.owner_type == owner_type.value,
                items.c.owner_id == owner_id,
            )
            .order_by(items.c.key, items.c.id)
        )
        return [item_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]

    def list_at_location(
        self, world_instance_id: WorldInstanceId, location_key: LocationKey
    ) -> list[Item]:
        stmt = (
            select(items)
            .where(
                items.c.world_instance_id == str(world_instance_id),
                items.c.location_key == str(location_key),
            )
            .order_by(items.c.key, items.c.id)
        )
        return [item_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]

    def find_stack(
        self,
        world_instance_id: WorldInstanceId,
        key: str,
        owner_type: ItemOwnerType,
        owner_id: str | None,
        location_key: LocationKey | None,
    ) -> Item | None:
        stmt = select(items).where(
            items.c.world_instance_id == str(world_instance_id),
            items.c.key == key,
            items.c.owner_type == owner_type.value,
            items.c.owner_id == owner_id,
            items.c.location_key == (None if location_key is None else str(location_key)),
        )
        row = self._session.execute(stmt).mappings().first()
        return None if row is None else item_from_row(dict(row))

    def save(self, item: Item) -> None:
        result = self._session.execute(
            update(items)
            .where(
                items.c.world_instance_id == str(item.world_instance_id),
                items.c.id == str(item.id),
            )
            .values(**item_row(item))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"item not found: {item.id}")

    def delete(self, item: Item) -> None:
        result = self._session.execute(
            delete(items).where(
                items.c.world_instance_id == str(item.world_instance_id),
                items.c.id == str(item.id),
            )
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"item not found: {item.id}")