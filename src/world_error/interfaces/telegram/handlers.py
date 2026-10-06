"""Thin aiogram message handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)


def build_router(adapter: TelegramAdapter) -> Router:
    router = Router(name="world-error-telegram")

    @router.message(F.chat.type.in_({"group", "supergroup"}))
    async def handle_group_message(message: Message) -> None:
        if message.from_user is None:
            await message.answer("A Telegram user account is required.")
            return
        await adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=message.chat.id,
                chat_type=message.chat.type,
                telegram_user_id=message.from_user.id,
                text=message.text,
            )
        )

    return router
