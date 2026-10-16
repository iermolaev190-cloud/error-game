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
COMMAND_EXECUTOR_INTENTS = frozenset(
    {
        IntentType.TAKE,
        IntentType.DROP,
        IntentType.TALK,
        IntentType.GIVE,
        IntentType.SHARE_KNOWLEDGE,
        IntentType.TRADE,
    }
)


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
                return "Диалог с NPC — только в DM. Напиши боту лично: /talk <npc>."
            if intent.type in {
                IntentType.GIVE,
                IntentType.SHARE_KNOWLEDGE,
                IntentType.TRADE,
            }:
                if intent.target is None:
                    return self._failure(
                        intent.type.value, "Укажи персонажа, которому адресована команда."
                    )
                counterparty_id = await asyncio.to_thread(
                    self._key_resolver.resolve_character,
                    world_instance_id,
                    character.location_key,
                    intent.target,
                )
                if counterparty_id is None:
                    npc_id = await asyncio.to_thread(
                        self._key_resolver.resolve_npc_in_instance,
                        world_instance_id,
                        intent.target,
                    )
                    if npc_id is not None:
                        return self._failure(
                            intent.type.value,
                            f"'{intent.target}' — это NPC, не игрок. "
                            "GIVE/SHARE/TRADE работают только между игроками. "
                            "Для общения с NPC — /talk в DM.",
                        )
                    return self._failure(
                        intent.type.value,
                        f"Не удалось найти персонажа '{intent.target}' здесь. "
                        "Проверь имя и убедись, что вы в одном мире и локации.",
                    )

                if intent.type is IntentType.GIVE:
                    item_key = intent.params.get("item_key")
                    if not isinstance(item_key, str):
                        return self._failure(
                            "GIVE", "Укажи предмет, который хочешь передать."
                        )
                    item_id = await asyncio.to_thread(
                        self._key_resolver.resolve_inventory_item,
                        world_instance_id,
                        character.id,
                        item_key,
                    )
                    if item_id is None:
                        return self._failure(
                            "GIVE",
                            f"У тебя нет '{item_key}' в инвентаре. Проверь /inventory в DM.",
                        )
                    result = await asyncio.to_thread(
                        self._world_engine.give_item,
                        world_instance_id,
                        giver_id=CharacterId(character.id),
                        receiver_id=counterparty_id,
                        item_id=item_id,
                    )
                elif intent.type is IntentType.SHARE_KNOWLEDGE:
                    information_key = intent.params.get("information_key")
                    if not isinstance(information_key, str):
                        return self._failure(
                            "SHARE", "Укажи информацию, которой хочешь поделиться."
                        )
                    known_information_key = await asyncio.to_thread(
                        self._key_resolver.resolve_known_information,
                        world_instance_id,
                        CharacterId(character.id),
                        information_key,
                    )
                    if known_information_key is None:
                        return self._failure(
                            "SHARE",
                            f"Ты не знаешь '{information_key}', поэтому поделиться этим "
                            "не получится. Проверь /knowledge в DM.",
                        )
                    result = await asyncio.to_thread(
                        self._world_engine.share_knowledge,
                        world_instance_id,
                        sharer_id=CharacterId(character.id),
                        receiver_id=counterparty_id,
                        information_key=known_information_key,
                    )
                else:
                    offered_item_key = intent.params.get("offered_item_key")
                    requested_item_key = intent.params.get("requested_item_key")
                    if not isinstance(offered_item_key, str) or not isinstance(
                        requested_item_key, str
                    ):
                        return self._failure(
                            "TRADE",
                            "Укажи предмет, который предлагаешь, и предмет для обмена.",
                        )
                    offered_item_id = await asyncio.to_thread(
                        self._key_resolver.resolve_inventory_item,
                        world_instance_id,
                        character.id,
                        offered_item_key,
                    )
                    if offered_item_id is None:
                        return self._failure(
                            "TRADE",
                            f"У тебя нет '{offered_item_key}' в инвентаре. "
                            "Проверь /inventory в DM.",
                        )
                    requested_item_id = await asyncio.to_thread(
                        self._key_resolver.resolve_inventory_item,
                        world_instance_id,
                        counterparty_id,
                        requested_item_key,
                    )
                    if requested_item_id is None:
                        return self._failure(
                            "TRADE",
                            f"У '{intent.target}' нет '{requested_item_key}' в инвентаре. "
                            "Проверьте предметы и попробуйте снова.",
                        )
                    result = await asyncio.to_thread(
                        self._world_engine.trade_items,
                        world_instance_id,
                        initiator_id=CharacterId(character.id),
                        counterparty_id=counterparty_id,
                        offered_item_id=offered_item_id,
                        requested_item_id=requested_item_id,
                    )
                return (
                    self._formatter.format_dm(result)
                    if private
                    else self._formatter.format(result)
                )

            if intent.type in {IntentType.TAKE, IntentType.DROP}:
                if intent.target is None:
                    return self._failure(
                        intent.type.value, "Укажи предмет, который хочешь взять или выбросить."
                    )
                if intent.type is IntentType.TAKE:
                    inventory_item_id = await asyncio.to_thread(
                        self._key_resolver.resolve_inventory_item,
                        world_instance_id,
                        character.id,
                        intent.target,
                    )
                    if inventory_item_id is not None:
                        return self._failure(
                            "TAKE",
                            f"У тебя уже есть '{intent.target}'. "
                            "Проверь /inventory в DM.",
                        )
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
                    if intent.type is IntentType.TAKE:
                        return self._failure(
                            "TAKE",
                            f"Здесь нет '{intent.target}'. Проверь /look в локации.",
                        )
                    return self._failure(
                        "DROP",
                        f"У тебя нет '{intent.target}' в инвентаре. "
                        "Проверь /inventory в DM.",
                    )
                intent = replace(intent, target=str(item_id))
            elif intent.type is IntentType.TALK:
                if intent.target is None:
                    return self._failure("TALK_TO_NPC", "Укажи NPC для разговора.")
                npc_id = await asyncio.to_thread(
                    self._key_resolver.resolve_npc,
                    world_instance_id,
                    character.location_key,
                    intent.target,
                )
                if npc_id is None:
                    return self._failure(
                        "TALK_TO_NPC",
                        f"Не удалось найти NPC '{intent.target}' в этой локации. "
                        "Проверь имя и /look.",
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
