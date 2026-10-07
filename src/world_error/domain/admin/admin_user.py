"""Technical allowlist entry for Telegram administration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AdminUser:
    telegram_user_id: int
    name: str
    added_by_telegram_id: int
    added_at: datetime
    active: bool
