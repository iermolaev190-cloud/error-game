"""Handle private Telegram messages without creating or selecting worlds client-side."""

from __future__ import annotations

import asyncio

from world_error.application.action_result import ActionResult
from world_error.application.ai.command_router import CommandRouter
from world_error.application.ai.interpreter import IntentContext, IntentInterpreter
from world_error.application.ai.key_resolver import InstanceKeyResolver
from world_error.application.ai.registry import INTENT_HANDLERS
from world_error.application.ports.telegram import TelegramClient
from world_error.application.queries.location_view import LocationView
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import Character
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    WorldInstanceId,
)
from world_error.interfaces.telegram.command_executor import TelegramCommandExecutor
from world_error.interfaces.telegram.formatter import TelegramFormatter
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class DmTelegramHandler:
    def __init__(
        self,
        *,
        telegram_client: TelegramClient,
        world_engine: WorldEngine,
        intent_interpreter: IntentInterpreter,
        instance_resolver: GroupInstanceResolver,
        formatter: TelegramFormatter,
        command_router: CommandRouter,
        command_executor: TelegramCommandExecutor,
    ) -> None:
        self._telegram_client = telegram_client
        self._world_engine = world_engine
        self._intent_interpreter = intent_interpreter
        self._instance_resolver = instance_resolver
        self._formatter = formatter
        self._command_router = command_router
        self._command_executor = command_executor

    async def handle_message(
        self, *, chat_id: int, telegram_user_id: int, text: str | None
    ) -> str:
        if not text or not text.strip():
            response = "Send a text command."
            await self._telegram_client.send_message(chat_id, response)
            return response

        try:
            instance_id = await asyncio.to_thread(
                self._instance_resolver.resolve_dm_instance, telegram_user_id
            )
        except DomainError as exc:
            await self._telegram_client.send_message(chat_id, exc.message)
            return exc.message

        character = await asyncio.to_thread(
            self._instance_resolver.resolve_dm_character,
            telegram_user_id,
            instance_id,
        )
        if character is None or character.world_instance_id != instance_id:
            response = "No active character is linked to your Telegram account in this world."
            await self._telegram_client.send_message(chat_id, response)
            return response

        command = text.strip()
        routed = self._command_router.route(
            command, actor_id=CharacterId(character.id)
        )
        if routed.kind != "none":
            response = await self._command_executor.execute(
                routed,
                world_instance_id=instance_id,
                character=character,
                private=True,
            )
        else:
            result = await self._interpret_and_execute(
                command,
                telegram_user_id,
                instance_id,
                character,
            )
            response = self._formatter.format_dm(result)
        await self._telegram_client.send_message(chat_id, response)
        return response

    async def _interpret_and_execute(
        self,
        raw_input: str,
        telegram_user_id: int,
        instance_id: WorldInstanceId,
        character: Character,
    ) -> ActionResult:
        location = await asyncio.to_thread(
            self._world_engine.view_location,
            instance_id,
            observer_id=character.id,
            location_key=character.location_key,
        )
        context = IntentContext(
            player_id=str(telegram_user_id),
            character_id=character.id,
            location_id=str(character.location_key),
            visible_objects=tuple(
                [presence.character_id for presence in location.characters]
                + [presence.npc_id for presence in location.npcs]
                + [item.key for item in location.items]
            ),
            allowed_actions=tuple(intent_type.value for intent_type in INTENT_HANDLERS),
        )

        intent = await asyncio.to_thread(
            self._intent_interpreter.interpret,
            raw_input,
            context,
        )
        if intent is None:
            return ActionResult.failure(
                "INTERPRET",
                DomainError(
                    ErrorCode.INVALID_ACTION,
                    "input could not be interpreted as a supported intent",
                ),
            )
        return await asyncio.to_thread(
            self._world_engine.handle_intent,
            instance_id,
            CharacterId(character.id),
            intent,
        )
