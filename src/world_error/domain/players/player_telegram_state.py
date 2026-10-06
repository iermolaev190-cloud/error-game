"""Technical Telegram routing state for a player."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PlayerTelegramState:
    telegram_user_id: int
    last_group_chat_id: int | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.telegram_user_id <= 0:
            raise ValueError("telegram_user_id must be positive")
        if self.last_group_chat_id is not None and self.last_group_chat_id >= 0:
            raise ValueError("last_group_chat_id must identify a Telegram group")
