"""Репозиторий информационных объектов мира."""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.information.information import Information
from world_error.domain.shared.kernel import DomainError, ErrorCode, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import (
    information_from_row,
    information_row,
)
from world_error.infrastructure.db.tables import information


class SqlInformationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: Information) -> None:
        self._session.execute(insert(information).values(**information_row(item)))

    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Information:
        row = (
            self._session.execute(
                select(information).where(
                    information.c.world_instance_id == str(world_instance_id),
                    information.c.key == key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"information not found: {key}")
        return information_from_row(dict(row))

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> list[Information]:
        stmt = (
            select(information)
            .where(information.c.world_instance_id == str(world_instance_id))
            .order_by(information.c.key)
        )
        return [information_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]

    def save(self, item: Information) -> None:
        result = self._session.execute(
            update(information)
            .where(
                information.c.world_instance_id == str(item.world_instance_id),
                information.c.id == str(item.id),
            )
            .values(**information_row(item))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"information not found: {item.key}")
