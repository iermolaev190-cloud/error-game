"""SQL repository for Telegram chat bindings."""

from __future__ import annotations

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from world_error.application.ports.chat_bindings import ChatBinding
from world_error.domain.shared.kernel import WorldInstanceId
from world_error.infrastructure.db.tables import chat_bindings


class SqlChatBindingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, binding: ChatBinding) -> None:
        self._session.execute(
            insert(chat_bindings).values(
                telegram_chat_id=binding.telegram_chat_id,
                world_instance_id=str(binding.world_instance_id),
                created_at=binding.created_at,
            )
        )

    def get_by_telegram_chat_id(self, telegram_chat_id: int) -> ChatBinding | None:
        row = (
            self._session.execute(
                select(chat_bindings).where(
                    chat_bindings.c.telegram_chat_id == telegram_chat_id
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return ChatBinding(
            telegram_chat_id=row["telegram_chat_id"],
            world_instance_id=WorldInstanceId(row["world_instance_id"]),
            created_at=row["created_at"],
        )
