"""Normalize group messages and route them through application services."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from world_error.application.action_result import ActionResult
from world_error.application.ai.interpreter import IntentContext, IntentInterpreter
from world_error.application.ai.intent import IntentType
from world_error.application.ai.registry import INTENT_HANDLERS
from world_error.application.ports.telegram import TelegramClient
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    WorldInstanceId,
)
from world_error.interfaces.telegram.dm_handler import DmTelegramHandler
from world_error.interfaces.telegram.formatter import TelegramFormatter
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


@dataclass(frozen=True, slots=True)
class TelegramIncomingMessage:
    chat_id: int
    chat_type: str
    telegram_user_id: int
    text: str | None


class TelegramAdapter:
    def __init__(
        self,
        *,
        telegram_client: TelegramClient,
        world_engine: WorldEngine,
        intent_interpreter: IntentInterpreter,
        instance_resolver: GroupInstanceResolver,
        formatter: TelegramFormatter | None = None,
        dm_handler: DmTelegramHandler | None = None,
    ) -> None:
        self._telegram_client = telegram_client
        self._world_engine = world_engine
        self._intent_interpreter = intent_interpreter
        self._instance_resolver = instance_resolver
        self._formatter = formatter or TelegramFormatter()
        self._dm_handler = dm_handler or DmTelegramHandler(
            telegram_client=telegram_client,
            world_engine=world_engine,
            intent_interpreter=intent_interpreter,
            instance_resolver=instance_resolver,
            formatter=self._formatter,
        )

    async def handle_message(self, update: TelegramIncomingMessage) -> str:
        if update.chat_type == "private":
            return await self._dm_handler.handle_message(
                chat_id=update.chat_id,
                telegram_user_id=update.telegram_user_id,
                text=update.text,
            )
        if update.chat_type not in {"group", "supergroup"}:
            return "This bot supports group and private chats only."

        world_instance_id = await asyncio.to_thread(
            self._instance_resolver.resolve,
            update.chat_id,
            chat_type=update.chat_type,
            create_if_missing=True,
        )
        if world_instance_id is None:
            response = "This group could not be connected to a WORLD INSTANCE."
            await self._telegram_client.send_message(update.chat_id, response)
            return response
        await asyncio.to_thread(
            self._instance_resolver.record_last_group_chat,
            update.telegram_user_id,
            update.chat_id,
        )
        if not update.text or not update.text.strip():
            response = "Send a text command."
            await self._telegram_client.send_message(update.chat_id, response)
            return response

        character = await asyncio.to_thread(
            self._world_engine.find_active_character_for_player,
            world_instance_id,
            str(update.telegram_user_id),
        )
        if character is None:
            response = (
                "No active character is linked to your Telegram account in this world. "
                "Ask an administrator to create or link one."
            )
            await self._telegram_client.send_message(update.chat_id, response)
            return response

        location = await asyncio.to_thread(
            self._world_engine.view_location,
            world_instance_id,
            observer_id=character.id,
            location_key=character.location_key,
        )
        context = IntentContext(
            player_id=str(update.telegram_user_id),
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
            update.text,
            context,
        )
        if intent is None:
            result = ActionResult.failure(
                "INTERPRET",
                DomainError(
                    ErrorCode.INVALID_ACTION,
                    "input could not be interpreted as a supported intent",
                ),
            )
        elif intent.type is IntentType.TALK:
            result = ActionResult.failure(
                "TELEGRAM_GROUP",
                DomainError(
                    ErrorCode.NOT_ALLOWED,
                    "NPC dialogue is not available in group chats",
                ),
            )
        else:
            result = await asyncio.to_thread(
                self._world_engine.handle_intent,
                WorldInstanceId(world_instance_id),
                CharacterId(character.id),
                intent,
            )
        response = self._formatter.format(result)
        await self._telegram_client.send_message(update.chat_id, response)
        return response
