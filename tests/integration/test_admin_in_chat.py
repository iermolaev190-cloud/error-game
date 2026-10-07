import asyncio

from world_error.domain.admin.admin_user import AdminUser
from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "group", "title": "Admin"})()


def send_admin(adapter: TelegramAdapter, chat_id: int, user_id: int, text: str) -> str:
    return asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=chat_id,
                chat_type="supergroup",
                telegram_user_id=user_id,
                text=text,
            )
        )
    )


def test_admin_chat_read_commands_and_admin_management(world_engine, uow_factory) -> None:
    admin_chat_id = -9910
    admin_user_id = 9910
    world = world_engine.create_instance(telegram_chat_id=-9911, seed=11)
    character = world_engine.create_character(
        world.id,
        player_id="9911",
        name="Inspectable Player",
        location_key=LocationKey("base"),
    )
    assert character.ok
    with uow_factory() as uow:
        uow.admin_users.add(
            AdminUser(
                telegram_user_id=admin_user_id,
                name="Primary Admin",
                added_by_telegram_id=0,
                added_at=world.created_at,
                active=True,
            )
        )
        uow.commit()
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=object(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
        admin_chat_id=admin_chat_id,
    )

    worlds = send_admin(adapter, admin_chat_id, admin_user_id, "/admin worlds")
    instance = send_admin(
        adapter, admin_chat_id, admin_user_id, f"/admin instance {world.id}"
    )
    events = send_admin(
        adapter, admin_chat_id, admin_user_id, f"/admin events {world.id}"
    )
    character_response = send_admin(
        adapter,
        admin_chat_id,
        admin_user_id,
        f"/admin character {world.id} {character.payload['character_id']}",
    )
    location = send_admin(
        adapter, admin_chat_id, admin_user_id, f"/admin location {world.id} base"
    )
    added = send_admin(
        adapter, admin_chat_id, admin_user_id, "/add-admin 9912 Secondary Admin"
    )
    admins = send_admin(adapter, admin_chat_id, admin_user_id, "/admin admins")
    removed = send_admin(adapter, admin_chat_id, admin_user_id, "/remove-admin 9912")

    assert str(world.id) in worlds
    assert f"INSTANCE {world.id}" in instance
    assert "EVENT" in events
    assert "Inspectable Player" in character_response
    assert "LOCATION base" in location
    assert added == "Администратор 9912 добавлен."
    assert "ADMIN 9912 name=Secondary Admin status=active" in admins
    assert removed == "Администратор 9912 деактивирован."
    assert client.sent[-1] == (admin_chat_id, removed)
    with uow_factory() as uow:
        assert uow.chat_bindings.get_by_telegram_chat_id(admin_chat_id) is None
        secondary = uow.admin_users.get(9912)
    assert secondary is not None and not secondary.active


def test_non_admin_is_denied_in_configured_admin_chat(
    world_engine, uow_factory
) -> None:
    admin_chat_id = -9913
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=object(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
        admin_chat_id=admin_chat_id,
    )

    response = send_admin(adapter, admin_chat_id, 9914, "/admin worlds")

    assert response == "Доступ запрещён."
    with uow_factory() as uow:
        assert uow.chat_bindings.get_by_telegram_chat_id(admin_chat_id) is None
