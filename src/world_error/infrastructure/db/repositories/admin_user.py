"""SQL repository for technical Telegram administrators."""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import insert, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from world_error.domain.admin.admin_user import AdminUser
from world_error.infrastructure.db.repositories._mapping import as_utc
from world_error.infrastructure.db.tables import admin_users


class SqlAdminUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, admin_user: AdminUser) -> None:
        self._session.execute(
            insert(admin_users).values(**self._row_values(admin_user))
        )

    def get(self, telegram_user_id: int) -> AdminUser | None:
        row = (
            self._session.execute(
                select(admin_users).where(
                    admin_users.c.telegram_user_id == telegram_user_id
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else self._from_row(row)

    def list_all(self) -> tuple[AdminUser, ...]:
        rows = (
            self._session.execute(
                select(admin_users).order_by(admin_users.c.telegram_user_id)
            )
            .mappings()
            .all()
        )
        return tuple(self._from_row(row) for row in rows)

    def save(self, admin_user: AdminUser) -> None:
        self._session.execute(
            update(admin_users)
            .where(admin_users.c.telegram_user_id == admin_user.telegram_user_id)
            .values(**self._row_values(admin_user))
        )

    @staticmethod
    def _row_values(admin_user: AdminUser) -> dict[str, object]:
        return {
            "telegram_user_id": admin_user.telegram_user_id,
            "name": admin_user.name,
            "added_by_telegram_id": admin_user.added_by_telegram_id,
            "added_at": admin_user.added_at.astimezone(timezone.utc),
            "active": admin_user.active,
        }

    @staticmethod
    def _from_row(row: RowMapping) -> AdminUser:
        return AdminUser(
            telegram_user_id=row["telegram_user_id"],
            name=row["name"],
            added_by_telegram_id=row["added_by_telegram_id"],
            added_at=as_utc(row["added_at"]),
            active=row["active"],
        )
