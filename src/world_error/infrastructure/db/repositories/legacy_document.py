"""World-instance scoped legacy documents, separate from character inventory."""

from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from world_error.domain.legacy.legacy_document import LegacyDocument
from world_error.domain.shared.kernel import DomainError, ErrorCode, LegacyDocumentId, LocationKey, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import (
    legacy_document_from_row,
    legacy_document_row,
)
from world_error.infrastructure.db.tables import legacy_items


class SqlLegacyDocumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, document: LegacyDocument) -> None:
        self._session.execute(insert(legacy_items).values(**legacy_document_row(document)))

    def get(
        self, world_instance_id: WorldInstanceId, document_id: LegacyDocumentId
    ) -> LegacyDocument:
        row = (
            self._session.execute(
                select(legacy_items).where(
                    legacy_items.c.world_instance_id == str(world_instance_id),
                    legacy_items.c.id == str(document_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"legacy document not found: {document_id}")
        return legacy_document_from_row(dict(row))

    def list_at_location(
        self, world_instance_id: WorldInstanceId, location_key: LocationKey
    ) -> list[LegacyDocument]:
        rows = self._session.execute(
            select(legacy_items)
            .where(
                legacy_items.c.world_instance_id == str(world_instance_id),
                legacy_items.c.location_key == str(location_key),
            )
            .order_by(legacy_items.c.seq)
        ).mappings()
        return [legacy_document_from_row(dict(row)) for row in rows]
