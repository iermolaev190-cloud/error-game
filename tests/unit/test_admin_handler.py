import asyncio
from datetime import datetime, timezone

from world_error.bootstrap.config import Settings
from world_error.domain.admin.admin_user import AdminUser
from world_error.interfaces.telegram.admin_handler import AdminTelegramHandler


class MockTelegramClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "group", "title": "Admin"})()


def test_admin_handler_authorizes_user_and_routes_admin_query(
    world_engine, uow_factory
) -> None:
    admin_chat_id = -9901
    telegram_user_id = 9901
    world = world_engine.create_instance(telegram_chat_id=-9902, seed=2)
    with uow_factory() as uow:
        uow.admin_users.add(
            AdminUser(
                telegram_user_id=telegram_user_id,
                name="Admin",
                added_by_telegram_id=0,
                added_at=datetime.now(timezone.utc),
                active=True,
            )
        )
        uow.commit()
    client = MockTelegramClient()
    handler = AdminTelegramHandler(
        telegram_client=client,
        world_engine=world_engine,
        uow_factory=uow_factory,
        admin_chat_id=admin_chat_id,
    )

    response = asyncio.run(
        handler.handle_message(
            chat_id=admin_chat_id,
            telegram_user_id=telegram_user_id,
            text="/admin instance " + str(world.id),
        )
    )

    assert f"INSTANCE {world.id}" in response
    assert "world_tick=0" in response
    assert client.sent == [(admin_chat_id, response)]


def test_admin_handler_rejects_inactive_user(world_engine, uow_factory) -> None:
    admin_chat_id = -9903
    with uow_factory() as uow:
        uow.admin_users.add(
            AdminUser(
                telegram_user_id=9903,
                name="Inactive",
                added_by_telegram_id=0,
                added_at=datetime.now(timezone.utc),
                active=False,
            )
        )
        uow.commit()
    handler = AdminTelegramHandler(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        uow_factory=uow_factory,
        admin_chat_id=admin_chat_id,
    )

    response = asyncio.run(
        handler.handle_message(
            chat_id=admin_chat_id,
            telegram_user_id=9903,
            text="/admin worlds",
        )
    )

    assert response == "Доступ запрещён."


def test_settings_load_admin_chat_id_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("WORLD_ERROR_ADMIN_CHAT_ID", "-9919")

    settings = Settings(_env_file=None)

    assert settings.admin_chat_id == -9919
