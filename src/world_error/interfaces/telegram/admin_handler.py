"""Read-only Telegram administration in its configured private admin group."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from world_error.application.ports.repositories import UnitOfWork
from world_error.application.ports.telegram import TelegramClient
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.admin.admin_user import AdminUser
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    LocationKey,
    NpcId,
    WorldInstanceId,
)

_HELP = (
    "Admin-команды:\n"
    "/admin worlds\n"
    "/admin instance <world_id>\n"
    "/admin events <world_id> [N]\n"
    "/admin character <world_id> <char_id>\n"
    "/admin npc <world_id> <npc_id>\n"
    "/admin location <world_id> <key>\n"
    "/admin admins\n"
    "/add-admin <telegram_id> <name>\n"
    "/remove-admin <telegram_id>"
)


class AdminTelegramHandler:
    def __init__(
        self,
        *,
        telegram_client: TelegramClient,
        world_engine: WorldEngine,
        uow_factory: Callable[[], UnitOfWork],
        admin_chat_id: int | None,
    ) -> None:
        self._telegram_client = telegram_client
        self._world_engine = world_engine
        self._uow_factory = uow_factory
        self._admin_chat_id = admin_chat_id

    async def handle_message(
        self, *, chat_id: int, telegram_user_id: int, text: str | None
    ) -> str:
        response = await asyncio.to_thread(
            self._handle_sync,
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            text=text,
        )
        if response:
            await self._telegram_client.send_message(chat_id, response)
        return response

    def _handle_sync(
        self, *, chat_id: int, telegram_user_id: int, text: str | None
    ) -> str:
        if self._admin_chat_id is None or chat_id != self._admin_chat_id:
            return "Admin-команды доступны только в настроенном admin-чате."

        with self._uow_factory() as uow:
            admin = uow.admin_users.get(telegram_user_id)
        if admin is None or not admin.active:
            return "Доступ запрещён."
        if not text or not text.strip():
            return _HELP

        parts = text.strip().split()
        command = parts[0].split("@", maxsplit=1)[0].casefold()
        try:
            if command == "/admin":
                return self._admin_command(parts[1:])
            if command == "/add-admin":
                return self._add_admin(text.strip(), telegram_user_id)
            if command == "/remove-admin":
                return self._remove_admin(parts[1:])
        except DomainError as exc:
            return f"Ошибка: {exc.code.value}: {exc.message}"
        return _HELP

    def _admin_command(self, args: list[str]) -> str:
        if not args:
            return _HELP
        subcommand = args[0].casefold()
        if subcommand == "worlds" and len(args) == 1:
            instances = self._world_engine.list_instances()
            if not instances:
                return "WORLD INSTANCE отсутствуют."
            return "\n".join(
                f"INSTANCE {instance.id} lifecycle={instance.lifecycle.value} "
                f"world_tick={instance.state.world_tick} "
                f"state_version={instance.state.state_version}"
                for instance in instances
            )
        if subcommand == "instance" and len(args) == 2:
            instance = self._world_engine.get_instance(WorldInstanceId(args[1]))
            return (
                f"INSTANCE {instance.id}\n"
                f"lifecycle={instance.lifecycle.value}\n"
                f"environment={instance.environment.value}\n"
                f"world_tick={instance.state.world_tick}\n"
                f"state_version={instance.state.state_version}\n"
                f"world_time={self._world_engine.get_world_time(instance.id).isoformat()}"
            )
        if subcommand == "events" and len(args) in {2, 3}:
            limit = 20
            if len(args) == 3:
                try:
                    limit = int(args[2])
                except ValueError:
                    return "N должно быть целым числом от 1 до 100."
            if not 1 <= limit <= 100:
                return "N должно быть целым числом от 1 до 100."
            events = self._world_engine.get_events(WorldInstanceId(args[1]))
            selected = events[-limit:]
            if not selected:
                return "Событий нет."
            return "\n".join(
                f"EVENT {event.id} {event.type.value} "
                f"created_at={event.created_at.isoformat()} "
                f"actor={event.actor or '-'} target={event.target or '-'} "
                f"result={event.result or '-'}"
                for event in selected
            )
        if subcommand == "character" and len(args) == 3:
            world_id = WorldInstanceId(args[1])
            character = self._world_engine.get_character(
                world_id, CharacterId(args[2])
            )
            return (
                f"CHARACTER {character.id}\n"
                f"world_instance_id={character.world_instance_id}\n"
                f"name={character.name}\n"
                f"player_id={character.player_id}\n"
                f"lifecycle={character.lifecycle.value}\n"
                f"activity={character.activity.value}\n"
                f"location={character.location_key}"
            )
        if subcommand == "npc" and len(args) == 3:
            npc = self._world_engine.get_npc(
                WorldInstanceId(args[1]), NpcId(args[2])
            )
            return (
                f"NPC {npc.id}\n"
                f"world_instance_id={npc.world_instance_id}\n"
                f"key={npc.key}\n"
                f"location={npc.location_key}\n"
                f"status={npc.status.value}"
            )
        if subcommand == "location" and len(args) == 3:
            world_id = WorldInstanceId(args[1])
            key = LocationKey(args[2])
            locations = self._world_engine.get_locations(world_id)
            location = next((item for item in locations if item.key == key), None)
            if location is None:
                return f"Локация '{key}' не найдена в INSTANCE {world_id}."
            return (
                f"LOCATION {location.key}\n"
                f"world_instance_id={location.world_instance_id}\n"
                f"discovery_state={location.discovery_state.value}\n"
                f"first_visited_at="
                f"{location.first_visited_at.isoformat() if location.first_visited_at else '-'}\n"
                f"updated_at={location.updated_at.isoformat()}"
            )
        if subcommand == "admins" and len(args) == 1:
            with self._uow_factory() as uow:
                admins = uow.admin_users.list_all()
            if not admins:
                return "Администраторов нет."
            return "\n".join(self._format_admin(admin) for admin in admins)
        return _HELP

    def _add_admin(self, text: str, added_by: int) -> str:
        parts = text.split(maxsplit=2)
        if len(parts) != 3:
            return "Использование: /add-admin <telegram_id> <name>"
        try:
            telegram_id = int(parts[1])
        except ValueError:
            return "telegram_id должен быть положительным целым числом."
        name = parts[2].strip()
        if telegram_id <= 0 or not name:
            return "telegram_id должен быть положительным, name — непустым."

        now = datetime.now(timezone.utc)
        with self._uow_factory() as uow:
            existing = uow.admin_users.get(telegram_id)
            if existing is not None and existing.active:
                return f"Администратор {telegram_id} уже активен."
            admin = AdminUser(
                telegram_user_id=telegram_id,
                name=name,
                added_by_telegram_id=added_by,
                added_at=now,
                active=True,
            )
            if existing is None:
                uow.admin_users.add(admin)
            else:
                uow.admin_users.save(admin)
            uow.commit()
        return f"Администратор {telegram_id} добавлен."

    def _remove_admin(self, args: list[str]) -> str:
        if len(args) != 1:
            return "Использование: /remove-admin <telegram_id>"
        try:
            telegram_id = int(args[0])
        except ValueError:
            return "telegram_id должен быть положительным целым числом."
        if telegram_id <= 0:
            return "telegram_id должен быть положительным целым числом."

        with self._uow_factory() as uow:
            existing = uow.admin_users.get(telegram_id)
            if existing is None or not existing.active:
                return f"Активный администратор {telegram_id} не найден."
            uow.admin_users.save(replace(existing, active=False))
            uow.commit()
        return f"Администратор {telegram_id} деактивирован."

    @staticmethod
    def _format_admin(admin: AdminUser) -> str:
        state = "active" if admin.active else "inactive"
        return f"ADMIN {admin.telegram_user_id} name={admin.name} status={state}"
