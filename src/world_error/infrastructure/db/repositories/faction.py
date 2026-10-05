"""Repository for instance-scoped factions and their location keys."""

from __future__ import annotations

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.factions.faction import Faction
from world_error.domain.shared.kernel import DomainError, ErrorCode, FactionId, LocationKey, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import faction_from_row, faction_row
from world_error.infrastructure.db.tables import faction_locations, factions


class SqlFactionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, faction: Faction) -> None:
        self._session.execute(insert(factions).values(**faction_row(faction)))
        self._replace_locations(faction)

    def get(self, world_instance_id: WorldInstanceId, faction_id: FactionId) -> Faction:
        row = (
            self._session.execute(
                select(factions).where(
                    factions.c.world_instance_id == str(world_instance_id),
                    factions.c.id == str(faction_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"faction not found: {faction_id}")
        return self._from_row(dict(row))

    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Faction:
        row = (
            self._session.execute(
                select(factions).where(
                    factions.c.world_instance_id == str(world_instance_id),
                    factions.c.key == key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"faction not found: {key}")
        return self._from_row(dict(row))

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> list[Faction]:
        rows = (
            self._session.execute(
                select(factions)
                .where(factions.c.world_instance_id == str(world_instance_id))
                .order_by(factions.c.key)
            )
            .mappings()
            .all()
        )
        return [self._from_row(dict(row)) for row in rows]

    def save(self, faction: Faction) -> None:
        result = self._session.execute(
            update(factions)
            .where(
                factions.c.world_instance_id == str(faction.world_instance_id),
                factions.c.id == str(faction.id),
            )
            .values(**faction_row(faction))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"faction not found: {faction.id}")
        self._replace_locations(faction)

    def _from_row(self, row: dict) -> Faction:
        location_rows = (
            self._session.execute(
                select(faction_locations.c.location_key)
                .where(
                    faction_locations.c.world_instance_id == row["world_instance_id"],
                    faction_locations.c.faction_id == row["id"],
                )
                .order_by(faction_locations.c.location_key)
            )
            .scalars()
            .all()
        )
        return faction_from_row(
            row, tuple(LocationKey(location_key) for location_key in location_rows)
        )

    def _replace_locations(self, faction: Faction) -> None:
        self._session.execute(
            delete(faction_locations).where(
                faction_locations.c.world_instance_id == str(faction.world_instance_id),
                faction_locations.c.faction_id == str(faction.id),
            )
        )
        if faction.location_keys:
            self._session.execute(
                insert(faction_locations),
                [
                    {
                        "world_instance_id": str(faction.world_instance_id),
                        "faction_id": str(faction.id),
                        "location_key": str(location_key),
                    }
                    for location_key in faction.location_keys
                ],
            )