"""Resolve Telegram group chats to their bound WORLD INSTANCE."""

from __future__ import annotations

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.shared.kernel import WorldInstanceId


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
