"""Transport port for the Telegram adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class TelegramChat:
    id: int
    type: str
    title: str | None = None


class TelegramClient(Protocol):
    async def send_message(self, chat_id: int, text: str) -> None: ...

    async def get_chat(self, chat_id: int) -> TelegramChat: ...
