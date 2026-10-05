"""Public faction projection with hidden content excluded by its shape."""

from __future__ import annotations

from dataclasses import dataclass

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.shared.kernel import WorldInstanceId


@dataclass(frozen=True, slots=True)
class FactionView:
    world_instance_id: str
    faction_id: str
    key: str
    name: str
    description: str
    faction_type: str
    public_goal: str
    status: str
    locations: tuple[str, ...]


class FactionViewQuery:
    def __init__(self, uow_factory: UnitOfWorkFactory, catalog: ContentCatalog) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> tuple[FactionView, ...]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            factions = uow.factions.list_for_instance(world_instance_id)
            views: list[FactionView] = []
            for faction in factions:
                definition = self._catalog.faction_definition(faction.key)
                views.append(
                    FactionView(
                        world_instance_id=str(faction.world_instance_id),
                        faction_id=str(faction.id),
                        key=faction.key,
                        name=definition.name,
                        description=definition.description,
                        faction_type=definition.faction_type,
                        public_goal=definition.public_goal,
                        status=faction.status.value,
                        locations=tuple(str(key) for key in faction.location_keys),
                    )
                )
            return tuple(views)
