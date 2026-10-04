"""Репозиторий instance-состояния локаций."""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.locations.location import LocationState
from world_error.domain.shared.kernel import DomainError, ErrorCode, LocationKey, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import (
    location_from_row,
    location_row,
)
from world_error.infrastructure.db.tables import location_states


class SqlLocationStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, state: LocationState) -> None:
        self._session.execute(insert(location_states).values(**location_row(state)))

    def get(self, world_instance_id: WorldInstanceId, key: LocationKey) -> LocationState:
        row = (
            self._session.execute(
                select(location_states).where(
                    location_states.c.world_instance_id == str(world_instance_id),
                    location_states.c.key == str(key),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"location state not found: {key}")
        return location_from_row(dict(row))

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> list[LocationState]:
        stmt = (
            select(location_states)
            .where(location_states.c.world_instance_id == str(world_instance_id))
            .order_by(location_states.c.key)
        )
        return [location_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]

    def save(self, state: LocationState) -> None:
        result = self._session.execute(
            update(location_states)
            .where(
                location_states.c.world_instance_id == str(state.world_instance_id),
                location_states.c.key == str(state.key),
            )
            .values(**location_row(state))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"location state not found: {state.key}")
