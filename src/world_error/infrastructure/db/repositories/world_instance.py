"""Репозиторий WORLD INSTANCE."""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.shared.kernel import DomainError, ErrorCode, WorldInstanceId
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.repositories._mapping import (
    instance_from_row,
    instance_row,
)
from world_error.infrastructure.db.tables import world_instances


class SqlWorldInstanceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, instance: WorldInstance) -> None:
        self._session.execute(insert(world_instances).values(**instance_row(instance)))

    def get(self, world_instance_id: WorldInstanceId) -> WorldInstance:
        row = (
            self._session.execute(
                select(world_instances).where(world_instances.c.id == str(world_instance_id))
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"world instance not found: {world_instance_id}")
        return instance_from_row(dict(row))

    def save(self, instance: WorldInstance) -> None:
        result = self._session.execute(
            update(world_instances)
            .where(world_instances.c.id == str(instance.id))
            .values(**instance_row(instance))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"world instance not found: {instance.id}")
