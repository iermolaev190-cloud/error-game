"""SQL repository for technical Telegram routing state."""

from __future__ import annotations

from datetime import timezone

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from world_error.domain.players.player_telegram_state import PlayerTelegramState
from world_error.infrastructure.db.repositories._mapping import as_utc
from world_error.infrastructure.db.tables import player_telegram_state


class SqlPlayerTelegramStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, telegram_user_id: int) -> PlayerTelegramState | None:
        row = (
            self._session.execute(
                select(player_telegram_state).where(
                    player_telegram_state.c.telegram_user_id == telegram_user_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return PlayerTelegramState(
            telegram_user_id=row["telegram_user_id"],
            last_group_chat_id=row["last_group_chat_id"],
            updated_at=as_utc(row["updated_at"]),
        )

    def save(self, state: PlayerTelegramState) -> None:
        values = {
            "last_group_chat_id": state.last_group_chat_id,
            "updated_at": state.updated_at.astimezone(timezone.utc),
        }
        dialect = self._session.get_bind().dialect.name
        if dialect == "sqlite":
            statement = sqlite_insert(player_telegram_state)
        elif dialect == "postgresql":
            statement = postgresql_insert(player_telegram_state)
        else:
            result = self._session.execute(
                update(player_telegram_state)
                .where(
                    player_telegram_state.c.telegram_user_id
                    == state.telegram_user_id
                )
                .values(**values)
            )
            if result.rowcount == 0:
                self._session.execute(
                    insert(player_telegram_state).values(
                        telegram_user_id=state.telegram_user_id,
                        **values,
                    )
                )
            return

        self._session.execute(
            statement.values(telegram_user_id=state.telegram_user_id, **values)
            .on_conflict_do_update(
                index_elements=[player_telegram_state.c.telegram_user_id],
                set_=values,
            )
        )
