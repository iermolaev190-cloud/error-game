"""Handle private Telegram messages without creating or selecting worlds client-side."""

from __future__ import annotations

import asyncio
import re

from world_error.application.action_result import ActionResult
from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.interpreter import IntentContext, IntentInterpreter
from world_error.application.ai.registry import INTENT_HANDLERS
from world_error.application.ports.telegram import TelegramClient
from world_error.application.queries.location_view import LocationView
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import Character
from world_error.domain.npcs.npc import Npc
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    NpcId,
    WorldInstanceId,
)
from world_error.interfaces.telegram.formatter import TelegramFormatter
from world_error.interfaces.telegram.resolver import GroupInstanceResolver

_TALK_COMMAND = re.compile(r"^talk\s+([a-z][a-z0-9_-]*)\s+(.+)$", re.IGNORECASE)


class DmTelegramHandler:
    def __init__(
        self,
        *,
        telegram_client: TelegramClient,
        world_engine: WorldEngine,
        intent_interpreter: IntentInterpreter,
        instance_resolver: GroupInstanceResolver,
        formatter: TelegramFormatter,
    ) -> None:
        self._telegram_client = telegram_client
        self._world_engine = world_engine
        self._intent_interpreter = intent_interpreter
        self._instance_resolver = instance_resolver
        self._formatter = formatter

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
        if command.casefold() == "inventory":
            result = await self._inventory_result(instance_id, character)
        elif command.casefold() == "knowledge":
            result = await self._knowledge_result(instance_id, character)
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

        talk_match = _TALK_COMMAND.fullmatch(raw_input)
        if talk_match is not None:
            npc = await self._find_visible_npc(
                instance_id, location, talk_match.group(1).casefold()
            )
            if npc is None:
                return ActionResult.failure(
                    "TALK_TO_NPC",
                    DomainError(ErrorCode.NOT_FOUND, "that NPC is not at your location"),
                )
            intent = Intent(
                type=IntentType.TALK,
                actor_id=character.id,
                target=str(npc.id),
                params={"message": talk_match.group(2).strip()},
            )
        else:
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
        if intent.type is IntentType.TALK and not isinstance(
            intent.params.get("message"), str
        ):
            return ActionResult.failure(
                "TALK_TO_NPC",
                DomainError(ErrorCode.INVALID_ACTION, "talk intent requires a message"),
            )
        return await asyncio.to_thread(
            self._world_engine.handle_intent,
            instance_id,
            CharacterId(character.id),
            intent,
        )

    async def _find_visible_npc(
        self, instance_id: WorldInstanceId, location: LocationView, key: str
    ) -> Npc | None:
        for presence in location.npcs:
            npc = await asyncio.to_thread(
                self._world_engine.get_npc,
                instance_id,
                NpcId(presence.npc_id),
            )
            if npc.key == key:
                return npc
        return None

    async def _inventory_result(
        self, instance_id: WorldInstanceId, character: Character
    ) -> ActionResult:
        inventory = await asyncio.to_thread(
            self._world_engine.get_inventory, instance_id, character.id
        )
        return ActionResult.success(
            "INVENTORY",
            payload={
                "inventory": tuple(
                    {
                        "name": item.name,
                        "quantity": item.quantity,
                        "description": item.description,
                    }
                    for item in inventory.items
                )
            },
        )

    async def _knowledge_result(
        self, instance_id: WorldInstanceId, character: Character
    ) -> ActionResult:
        knowledge = await asyncio.to_thread(
            self._world_engine.get_knowledge, instance_id, character.id
        )
        return ActionResult.success(
            "KNOWLEDGE",
            payload={
                "knowledge": tuple(
                    {
                        "claim": item.claim,
                        "claim_type": item.claim_type.value,
                        "confidence": item.confidence.value,
                        "document_date": (
                            None
                            if item.document_date is None
                            else item.document_date.isoformat()
                        ),
                    }
                    for item in knowledge
                )
            },
        )
