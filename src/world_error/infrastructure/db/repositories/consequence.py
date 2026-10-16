"""Репозиторий последствий вместе с их причинами (§26).

Причины — часть агрегата: последствие без причины не существует, поэтому
``add`` пишет строку и причины одной операцией, а чтение всегда собирает их
вместе.
"""

from __future__ import annotations

from sqlalchemy import and_, insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.consequences.consequence import (
    CONSEQUENCE_EVENT_PREFIX,
    Consequence,
)
from world_error.domain.shared.kernel import (
    ConsequenceId,
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
)
from world_error.infrastructure.db.repositories._mapping import (
    consequence_cause_row,
    consequence_from_row,
    consequence_row,
)
from world_error.infrastructure.db.tables import consequence_causes, consequences, events


class SqlConsequenceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, consequence: Consequence) -> None:
        self._session.execute(insert(consequences).values(**consequence_row(consequence)))
        for position, cause in enumerate(consequence.causes):
            self._session.execute(
                insert(consequence_causes).values(
                    **consequence_cause_row(consequence, cause, position)
                )
            )

    def get(
        self, world_instance_id: WorldInstanceId, consequence_id: ConsequenceId
    ) -> Consequence:
        rows = self._select_rows(world_instance_id, consequences.c.id == str(consequence_id))
        if not rows:
            raise DomainError(ErrorCode.NOT_FOUND, f"consequence not found: {consequence_id}")
        return self._hydrate(world_instance_id, rows)[0]

    def find_by_rule(
        self,
        world_instance_id: WorldInstanceId,
        rule_key: str,
        source_event_id: EventId,
    ) -> Consequence | None:
        """Сработало ли уже это правило на это событие (идемпотентность)."""
        rows = self._select_rows(
            world_instance_id,
            and_(
                consequences.c.rule_key == rule_key,
                consequences.c.source_event_id == str(source_event_id),
            ),
        )
        if not rows:
            return None
        return self._hydrate(world_instance_id, rows)[0]

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> list[Consequence]:
        return self._hydrate(world_instance_id, self._select_rows(world_instance_id))

    def list_pending(self, world_instance_id: WorldInstanceId) -> list[Consequence]:
        """Незакрытые последствия в порядке поступления (FIFO)."""
        return self._hydrate(
            world_instance_id,
            self._select_rows(world_instance_id, consequences.c.status == "PENDING"),
        )

    def list_caused_by(
        self, world_instance_id: WorldInstanceId, event_id: EventId
    ) -> list[Consequence]:
        """Все последствия, у которых среди причин есть это событие (ветвление, §25)."""
        return self._hydrate(
            world_instance_id,
            self._select_rows_via_causes(world_instance_id, str(event_id)),
        )

    def list_caused_by_consequence(
        self, world_instance_id: WorldInstanceId, consequence_id: ConsequenceId
    ) -> list[Consequence]:
        """Последствия, порождённые эффект-событиями указанного последствия."""
        stmt = (
            select(consequences)
            .join(
                consequence_causes,
                and_(
                    consequence_causes.c.consequence_id == consequences.c.id,
                    consequence_causes.c.world_instance_id == consequences.c.world_instance_id,
                ),
            )
            .join(
                events,
                and_(
                    events.c.id == consequence_causes.c.event_id,
                    events.c.world_instance_id == consequence_causes.c.world_instance_id,
                ),
            )
            .where(
                consequences.c.world_instance_id == str(world_instance_id),
                events.c.cause == f"{CONSEQUENCE_EVENT_PREFIX}{consequence_id}",
            )
            .order_by(consequences.c.seq)
        )
        rows = [dict(row) for row in self._session.execute(stmt).mappings().all()]
        return self._hydrate(world_instance_id, rows)

    def save(self, consequence: Consequence) -> None:
        result = self._session.execute(
            update(consequences)
            .where(
                consequences.c.world_instance_id == str(consequence.world_instance_id),
                consequences.c.id == str(consequence.id),
            )
            .values(
                status=consequence.status.value,
                applied_at=consequence.applied_at,
                applied_event_id=(
                    str(consequence.applied_event_id)
                    if consequence.applied_event_id is not None
                    else None
                ),
            )
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"consequence not found: {consequence.id}")

    # --- внутреннее ---------------------------------------------------------

    def _select_rows(self, world_instance_id: WorldInstanceId, *conditions) -> list[dict]:  # noqa: ANN002
        stmt = (
            select(consequences)
            .where(
                consequences.c.world_instance_id == str(world_instance_id),
                *conditions,
            )
            .order_by(consequences.c.seq)
        )
        return [dict(row) for row in self._session.execute(stmt).mappings().all()]

    def _select_rows_via_causes(
        self, world_instance_id: WorldInstanceId, event_id: str
    ) -> list[dict]:
        stmt = (
            select(consequences)
            .join(
                consequence_causes,
                and_(
                    consequence_causes.c.consequence_id == consequences.c.id,
                    consequence_causes.c.world_instance_id == consequences.c.world_instance_id,
                ),
            )
            .where(
                consequences.c.world_instance_id == str(world_instance_id),
                consequence_causes.c.event_id == event_id,
            )
            .order_by(consequences.c.seq)
        )
        return [dict(row) for row in self._session.execute(stmt).mappings().all()]

    def _hydrate(
        self, world_instance_id: WorldInstanceId, rows: list[dict]
    ) -> list[Consequence]:
        if not rows:
            return []
        ids = [str(row["id"]) for row in rows]
        cause_stmt = (
            select(consequence_causes)
            .where(
                consequence_causes.c.world_instance_id == str(world_instance_id),
                consequence_causes.c.consequence_id.in_(ids),
            )
            .order_by(consequence_causes.c.consequence_id, consequence_causes.c.position)
        )
        causes: dict[str, list[tuple[str, str]]] = {}
        for row in self._session.execute(cause_stmt).mappings().all():
            causes.setdefault(str(row["consequence_id"]), []).append(
                (str(row["event_id"]), str(row["origin"]))
            )
        return [
            consequence_from_row(row, causes.get(str(row["id"]), []))
            for row in rows
        ]
