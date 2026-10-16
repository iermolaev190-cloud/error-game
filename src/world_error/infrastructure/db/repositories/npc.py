"""Репозиторий NPC."""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.npcs.npc import Npc
from world_error.domain.shared.kernel import DomainError, ErrorCode, LocationKey, NpcId, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import npc_from_row, npc_row
from world_error.infrastructure.db.tables import npcs


class SqlNpcRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, npc: Npc) -> None:
        self._session.execute(insert(npcs).values(**npc_row(npc)))

    def get(self, world_instance_id: WorldInstanceId, npc_id: NpcId) -> Npc:
        row = (
            self._session.execute(
                select(npcs).where(
                    npcs.c.world_instance_id == str(world_instance_id),
                    npcs.c.id == str(npc_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"npc not found: {npc_id}")
        return npc_from_row(dict(row))

    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Npc:
        row = (
            self._session.execute(
                select(npcs).where(
                    npcs.c.world_instance_id == str(world_instance_id),
                    npcs.c.key == key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"npc not found: {key}")
        return npc_from_row(dict(row))

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> list[Npc]:
        stmt = (
            select(npcs)
            .where(npcs.c.world_instance_id == str(world_instance_id))
            .order_by(npcs.c.key)
        )
        return [npc_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]

    def list_in_location(
        self, world_instance_id: WorldInstanceId, location_key: LocationKey
    ) -> list[Npc]:
        """Все NPC этого мира, чья последняя известная локация совпадает.

        Фильтр по статусу (ACTIVE) делает вызывающий: ``MISSING`` NPC остаётся в
        этой локации лишь «последним известным местом» и в проекцию не попадает.
        """
        stmt = (
            select(npcs)
            .where(
                npcs.c.world_instance_id == str(world_instance_id),
                npcs.c.location_key == str(location_key),
            )
            .order_by(npcs.c.key)
        )
        return [npc_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]

    def save(self, npc: Npc) -> None:
        result = self._session.execute(
            update(npcs)
            .where(
                npcs.c.world_instance_id == str(npc.world_instance_id),
                npcs.c.id == str(npc.id),
            )
            .values(**npc_row(npc))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"npc not found: {npc.id}")
