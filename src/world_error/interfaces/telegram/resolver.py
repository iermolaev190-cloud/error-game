"""Resolve Telegram group chats to their bound WORLD INSTANCE."""

from __future__ import annotations

from datetime import datetime, timezone

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.characters.character import Character
from world_error.domain.players.player_telegram_state import PlayerTelegramState
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    WorldInstanceId,
)
from world_error.domain.world.instance import InstanceLifecycle


class GroupInstanceResolver:
    def __init__(
        self,
        world_engine: WorldEngine,
        uow_factory: UnitOfWorkFactory,
    ) -> None:
        self._world_engine = world_engine
        self._uow_factory = uow_factory

    def resolve(
        self,
        telegram_chat_id: int,
        *,
        chat_type: str,
        create_if_missing: bool,
    ) -> WorldInstanceId | None:
        if chat_type not in {"group", "supergroup"}:
            return None

        with self._uow_factory() as uow:
            binding = uow.chat_bindings.get_by_telegram_chat_id(telegram_chat_id)
        if binding is not None:
            return binding.world_instance_id
        if not create_if_missing:
            return None

        # Bootstrap: first group message creates INSTANCE + binding.
        # Not a player action. No TALK/MOVE events here.
        instance = self._world_engine.create_instance(telegram_chat_id)
        return instance.id

    def record_last_group_chat(self, telegram_user_id: int, chat_id: int) -> None:
        state = PlayerTelegramState(
            telegram_user_id=telegram_user_id,
            last_group_chat_id=chat_id,
            updated_at=datetime.now(timezone.utc),
        )
        with self._uow_factory() as uow:
            uow.player_telegram_state.save(state)
            uow.commit()

    def resolve_dm_instance(self, telegram_user_id: int) -> WorldInstanceId:
        with self._uow_factory() as uow:
            state = uow.player_telegram_state.get(telegram_user_id)
            if state is not None and state.last_group_chat_id is not None:
                binding = uow.chat_bindings.get_by_telegram_chat_id(
                    state.last_group_chat_id
                )
                if binding is None:
                    raise DomainError(
                        ErrorCode.NOT_FOUND,
                        "Your last group is no longer connected to a WORLD INSTANCE.",
                    )
                instance_id = binding.world_instance_id
            else:
                characters = uow.characters.list_active_by_player(
                    str(telegram_user_id)
                )

        if state is not None and state.last_group_chat_id is not None:
            instance = self._world_engine.get_instance(instance_id)
            if instance.lifecycle is not InstanceLifecycle.ACTIVE:
                raise DomainError(
                    ErrorCode.NOT_ALLOWED,
                    "Your last group is not connected to an active WORLD INSTANCE.",
                )
            return instance_id
        if not characters:
            raise DomainError(
                ErrorCode.NOT_FOUND,
                "Add the bot to a group before using it in a private chat.",
            )
        if len(characters) > 1:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                "You belong to multiple worlds; send a message in the group you want to use.",
            )
        instance_id = characters[0].world_instance_id
        instance = self._world_engine.get_instance(instance_id)
        if instance.lifecycle is not InstanceLifecycle.ACTIVE:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                "Your character is not in an active WORLD INSTANCE.",
            )
        return instance_id

    def resolve_dm_character(
        self, telegram_user_id: int, world_instance_id: WorldInstanceId
    ) -> Character | None:
        return self._world_engine.find_active_character_for_player(
            world_instance_id, str(telegram_user_id)
        )
