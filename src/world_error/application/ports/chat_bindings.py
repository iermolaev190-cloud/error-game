"""Application port for Telegram group to WORLD INSTANCE bindings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from world_error.domain.shared.kernel import WorldInstanceId


@dataclass(frozen=True, slots=True)
class ChatBinding:
    telegram_chat_id: int
    world_instance_id: WorldInstanceId
    created_at: datetime


class ChatBindingRepository(Protocol):
    def add(self, binding: ChatBinding) -> None: ...

    def get_by_telegram_chat_id(self, telegram_chat_id: int) -> ChatBinding | None: ...
