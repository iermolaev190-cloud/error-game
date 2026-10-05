"""Репозиторий знаний субъектов мира."""

from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from world_error.domain.knowledge.knowledge import Knowledge, SubjectType
from world_error.domain.shared.kernel import InformationId, KnowledgeId, DomainError, ErrorCode, WorldInstanceId
from world_error.infrastructure.db.repositories._mapping import (
    knowledge_from_row,
    knowledge_row,
)
from world_error.infrastructure.db.tables import knowledge


class SqlKnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: Knowledge) -> None:
        self._session.execute(insert(knowledge).values(**knowledge_row(item)))

    def get(self, world_instance_id: WorldInstanceId, knowledge_id: KnowledgeId) -> Knowledge:
        row = (
            self._session.execute(
                select(knowledge).where(
                    knowledge.c.world_instance_id == str(world_instance_id),
                    knowledge.c.id == str(knowledge_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"knowledge not found: {knowledge_id}")
        return knowledge_from_row(dict(row))

    def find(
        self,
        world_instance_id: WorldInstanceId,
        subject_type: SubjectType,
        subject_id: str,
        information_id: InformationId,
    ) -> Knowledge | None:
        row = (
            self._session.execute(
                select(knowledge).where(
                    knowledge.c.world_instance_id == str(world_instance_id),
                    knowledge.c.subject_type == subject_type.value,
                    knowledge.c.subject_id == subject_id,
                    knowledge.c.information_id == str(information_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else knowledge_from_row(dict(row))

    def list_for_subject(
        self,
        world_instance_id: WorldInstanceId,
        subject_type: SubjectType,
        subject_id: str,
    ) -> list[Knowledge]:
        stmt = (
            select(knowledge)
            .where(
                knowledge.c.world_instance_id == str(world_instance_id),
                knowledge.c.subject_type == subject_type.value,
                knowledge.c.subject_id == subject_id,
            )
            .order_by(knowledge.c.acquired_at, knowledge.c.id)
        )
        return [knowledge_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]
