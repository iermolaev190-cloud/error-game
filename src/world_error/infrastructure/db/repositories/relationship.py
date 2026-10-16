"""Репозиторий отношений между субъектами."""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipKind,
    SubjectRef,
)
from world_error.domain.shared.kernel import DomainError, ErrorCode, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import (
    relationship_from_row,
    relationship_row,
)
from world_error.infrastructure.db.tables import relationships


class SqlRelationshipRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, relationship: Relationship) -> None:
        self._session.execute(insert(relationships).values(**relationship_row(relationship)))

    def find(
        self,
        world_instance_id: WorldInstanceId,
        holder: SubjectRef,
        subject: SubjectRef,
        kind: RelationshipKind,
    ) -> Relationship | None:
        row = (
            self._session.execute(
                select(relationships).where(
                    relationships.c.world_instance_id == str(world_instance_id),
                    relationships.c.holder_type == holder.type.value,
                    relationships.c.holder_id == holder.id,
                    relationships.c.subject_type == subject.type.value,
                    relationships.c.subject_id == subject.id,
                    relationships.c.kind == kind.value,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else relationship_from_row(dict(row))

    def list_of(
        self, world_instance_id: WorldInstanceId, holder: SubjectRef
    ) -> list[Relationship]:
        """Что holder думает о других субъектах."""
        stmt = (
            select(relationships)
            .where(
                relationships.c.world_instance_id == str(world_instance_id),
                relationships.c.holder_type == holder.type.value,
                relationships.c.holder_id == holder.id,
            )
            .order_by(relationships.c.subject_type, relationships.c.subject_id, relationships.c.kind)
        )
        return [
            relationship_from_row(dict(row))
            for row in self._session.execute(stmt).mappings().all()
        ]

    def list_about(
        self, world_instance_id: WorldInstanceId, subject: SubjectRef
    ) -> list[Relationship]:
        """Кто и как относится к subject."""
        stmt = (
            select(relationships)
            .where(
                relationships.c.world_instance_id == str(world_instance_id),
                relationships.c.subject_type == subject.type.value,
                relationships.c.subject_id == subject.id,
            )
            .order_by(relationships.c.holder_type, relationships.c.holder_id, relationships.c.kind)
        )
        return [
            relationship_from_row(dict(row))
            for row in self._session.execute(stmt).mappings().all()
        ]

    def save(self, relationship: Relationship) -> None:
        result = self._session.execute(
            update(relationships)
            .where(
                relationships.c.world_instance_id == str(relationship.world_instance_id),
                relationships.c.id == str(relationship.id),
            )
            .values(**relationship_row(relationship))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"relationship not found: {relationship.id}")
