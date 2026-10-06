"""Execute routed Telegram actions and queries through application APIs."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from world_error.application.action_result import ActionResult
from world_error.application.ai.intent import IntentType
from world_error.application.ai.key_resolver import InstanceKeyResolver
from world_error.application.ai.routed_command import RoutedCommand
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import Character
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    WorldInstanceId,
)
from world_error.interfaces.telegram.formatter import TelegramFormatter

_PRIVATE_QUERIES = frozenset({"inventory", "knowledge", "character"})


class TelegramCommandExecutor:
    """Resolve command targets and route execution without parsing input text."""

    def __init__(
        self,
        *,
        world_engine: WorldEngine,
        key_resolver: InstanceKeyResolver,
        formatter: TelegramFormatter,
    ) -> None:
        self._world_engine = world_engine
        self._key_resolver = key_resolver
        self._formatter = formatter

    async def execute(
        self,
        command: RoutedCommand,
        *,
        world_instance_id: WorldInstanceId,
        character: Character,
        private: bool,
    ) -> str:
        if command.kind == "intent":
            assert command.intent is not None
            intent = command.intent
            if intent.type is IntentType.TALK and not private:
                return "Используй DM для приватных команд."
            if intent.type in {IntentType.TAKE, IntentType.DROP}:
                if intent.target is None:
                    return self._failure(intent.type.value, "item key is required")
                if intent.type is IntentType.TAKE:
                    item_id = await asyncio.to_thread(
                        self._key_resolver.resolve_location_item,
                        world_instance_id,
                        character.location_key,
                        intent.target,
                    )
                else:
                    item_id = await asyncio.to_thread(
                        self._key_resolver.resolve_inventory_item,
                        world_instance_id,
                        character.id,
                        intent.target,
                    )
                if item_id is None:
                    return self._failure(
                        intent.type.value,
                        f"item '{intent.target}' is not available here",
                    )
                intent = replace(intent, target=str(item_id))
            elif intent.type is IntentType.TALK:
                if intent.target is None:
                    return self._failure("TALK_TO_NPC", "NPC key is required")
                npc_id = await asyncio.to_thread(
                    self._key_resolver.resolve_npc,
                    world_instance_id,
                    character.location_key,
                    intent.target,
                )
                if npc_id is None:
                    return self._failure(
                        "TALK_TO_NPC",
                        f"NPC '{intent.target}' is not at your location",
                    )
                intent = replace(intent, target=str(npc_id))

            result = await asyncio.to_thread(
                self._world_engine.handle_intent,
                world_instance_id,
                CharacterId(character.id),
                intent,
            )
            return (
                self._formatter.format_dm(result)
                if private
                else self._formatter.format(result)
            )

        if command.kind != "query" or command.query_type is None:
            raise ValueError("only routed intent or query commands can be executed")

        query_type = command.query_type
        if query_type in _PRIVATE_QUERIES and not private:
            return "Используй DM для приватных команд."
        if query_type in {"look", "npcs"}:
            view = await asyncio.to_thread(
                self._world_engine.view_location,
                world_instance_id,
                observer_id=character.id,
                location_key=character.location_key,
            )
            return (
                self._formatter.format_location(view)
                if query_type == "look"
                else self._formatter.format_npcs(view)
            )
        if query_type == "inventory":
            inventory = await asyncio.to_thread(
                self._world_engine.get_inventory, world_instance_id, character.id
            )
            return self._formatter.format_inventory(inventory)
        if query_type == "knowledge":
            knowledge = await asyncio.to_thread(
                self._world_engine.get_knowledge, world_instance_id, character.id
            )
            return self._formatter.format_knowledge(knowledge)
        if query_type == "character":
            subject = await asyncio.to_thread(
                self._world_engine.get_character, world_instance_id, character.id
            )
            return self._formatter.format_character(subject)
        if query_type == "help":
            return self._formatter.format_help(private=private)
        raise ValueError(f"unsupported routed query: {query_type}")

    @staticmethod
    def _failure(action: str, message: str) -> str:
        result = ActionResult.failure(
            action,
            DomainError(ErrorCode.NOT_FOUND, message),
        )
        return TelegramFormatter().format(result)
