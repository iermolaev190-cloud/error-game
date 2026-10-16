"""DM-only character registration flow backed by aiogram FSM state."""

from __future__ import annotations

import asyncio

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.shared.kernel import DomainError, ErrorCode, WorldInstanceId
from world_error.interfaces.telegram.formatter import TelegramFormatter
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class RegistrationStates(StatesGroup):
    confirm = State()
    awaiting_name = State()
    done = State()


class RegistrationTelegramHandler:
    def __init__(
        self,
        *,
        world_engine: WorldEngine,
        instance_resolver: GroupInstanceResolver,
    ) -> None:
        self._world_engine = world_engine
        self._instance_resolver = instance_resolver

    async def start(self, *, telegram_user_id: int, state: FSMContext) -> str:
        await state.clear()
        try:
            instance_id = await asyncio.to_thread(
                self._instance_resolver.resolve_dm_instance, telegram_user_id
            )
        except DomainError as exc:
            if exc.code is ErrorCode.NOT_FOUND:
                return (
                    "Сначала добавь бота в игровую группу, затем напиши /start в личке."
                )
            return TelegramFormatter.friendly_error_message(exc.message)

        character = await asyncio.to_thread(
            self._instance_resolver.resolve_dm_character,
            telegram_user_id,
            instance_id,
        )
        if character is not None:
            await state.set_state(RegistrationStates.done)
            return self._welcome(character.name, str(character.location_key))

        await state.update_data(world_instance_id=str(instance_id))
        await state.set_state(RegistrationStates.confirm)
        return "У тебя нет character. Создать? Ответь «Да» или «Отмена»."

    async def confirm(
        self, *, telegram_user_id: int, text: str, state: FSMContext
    ) -> str:
        answer = text.strip().casefold()
        if answer in {"отмена", "отменить", "нет", "cancel"}:
            await state.clear()
            return "Ок. Напиши /start позже."
        if answer not in {"да", "yes"}:
            return "Ответь «Да» или «Отмена»."

        data = await state.get_data()
        world_instance_id = data.get("world_instance_id")
        if not isinstance(world_instance_id, str):
            await state.clear()
            return "Сессия регистрации завершилась. Напиши /start ещё раз."

        character = await asyncio.to_thread(
            self._world_engine.find_active_character_for_player,
            WorldInstanceId(world_instance_id),
            str(telegram_user_id),
        )
        if character is not None:
            await state.set_state(RegistrationStates.done)
            return self._welcome(character.name, str(character.location_key))

        await state.set_state(RegistrationStates.awaiting_name)
        return "Как тебя зовут?"

    async def create_character(
        self, *, telegram_user_id: int, text: str, state: FSMContext
    ) -> str:
        name = text.strip()
        if not name:
            return "Имя не должно быть пустым. Как тебя зовут?"

        data = await state.get_data()
        world_instance_id = data.get("world_instance_id")
        if not isinstance(world_instance_id, str):
            await state.clear()
            return "Сессия регистрации завершилась. Напиши /start ещё раз."

        typed_world_instance_id = WorldInstanceId(world_instance_id)
        character = await asyncio.to_thread(
            self._world_engine.find_active_character_for_player,
            typed_world_instance_id,
            str(telegram_user_id),
        )
        if character is not None:
            await state.set_state(RegistrationStates.done)
            return self._welcome(character.name, str(character.location_key))

        result = await asyncio.to_thread(
            self._world_engine.create_character,
            typed_world_instance_id,
            player_id=str(telegram_user_id),
            name=name,
            actor="system",
        )
        if not result.ok:
            await state.clear()
            message = result.error.message if result.error is not None else "unknown error"
            return f"Не удалось создать character: {message} Напиши /start, чтобы попробовать снова."

        await state.set_state(RegistrationStates.done)
        return self._welcome(
            str(result.payload["name"]),
            str(result.payload["location_key"]),
        )

    @staticmethod
    def _welcome(name: str, location_key: str) -> str:
        return f"Привет, {name}! Локация: {location_key}. /help."
