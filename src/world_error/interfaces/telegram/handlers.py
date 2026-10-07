"""Thin aiogram message handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.registration_handler import RegistrationStates


def build_router(adapter: TelegramAdapter) -> Router:
    router = Router(name="world-error-telegram")

    @router.message(F.chat.type == "private", CommandStart())
    async def handle_registration_start(
        message: Message, state: FSMContext
    ) -> None:
        if message.from_user is None:
            await message.answer("A Telegram user account is required.")
            return
        response = await adapter.registration_handler.start(
            telegram_user_id=message.from_user.id,
            state=state,
        )
        await message.answer(response)

    @router.message(F.chat.type == "private", RegistrationStates.confirm)
    async def handle_registration_confirmation(
        message: Message, state: FSMContext
    ) -> None:
        if message.from_user is None or message.text is None:
            await message.answer("Отправь текстовый ответ: «Да» или «Отмена».")
            return
        response = await adapter.registration_handler.confirm(
            telegram_user_id=message.from_user.id,
            text=message.text,
            state=state,
        )
        await message.answer(response)

    @router.message(F.chat.type == "private", RegistrationStates.awaiting_name)
    async def handle_registration_name(message: Message, state: FSMContext) -> None:
        if message.from_user is None or message.text is None:
            await message.answer("Отправь имя текстом.")
            return
        response = await adapter.registration_handler.create_character(
            telegram_user_id=message.from_user.id,
            text=message.text,
            state=state,
        )
        await message.answer(response)

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

    @router.message(F.chat.type == "private")
    async def handle_private_message(message: Message) -> None:
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
