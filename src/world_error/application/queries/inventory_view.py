"""Development inventory projection for an explicitly selected character."""

from __future__ import annotations

from dataclasses import dataclass

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.items.item import ItemOwnerType
from world_error.domain.shared.kernel import CharacterId, WorldInstanceId


@dataclass(frozen=True, slots=True)
class InventoryItemView:
    item_id: str
    key: str
    name: str
    description: str
    type: str
    weight: int
    quantity: int


@dataclass(frozen=True, slots=True)
class InventoryView:
    world_instance_id: str
    items: tuple[InventoryItemView, ...]


class InventoryViewQuery:
    """Read one character inventory; development CLI does not authenticate identity."""

    def __init__(self, uow_factory: UnitOfWorkFactory, catalog: ContentCatalog) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog

    def get(
        self, world_instance_id: WorldInstanceId, character_id: CharacterId
    ) -> InventoryView:
        with self._uow_factory() as uow:
            uow.characters.get(world_instance_id, character_id)
            items = uow.items.list_by_owner(
                world_instance_id, ItemOwnerType.CHARACTER, str(character_id)
            )
            views = []
            for item in items:
                definition = self._catalog.item_definition(item.key)
                views.append(
                    InventoryItemView(
                        item_id=str(item.id),
                        key=item.key,
                        name=definition.name,
                        description=definition.description,
                        type=definition.type.value,
                        weight=definition.weight,
                        quantity=item.quantity,
                    )
                )
            return InventoryView(
                world_instance_id=str(world_instance_id),
                items=tuple(views),
            )