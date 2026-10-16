import asyncio
from datetime import datetime, timezone

from world_error.domain.admin.admin_user import AdminUser
from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    async def send_message(self, chat_id: int, text: str) -> None:
        pass

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "group", "title": "Admin"})()


def send(
    adapter: TelegramAdapter,
    *,
    chat_id: int,
    chat_type: str,
    user_id: int,
    text: str,
) -> str:
    return asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=chat_id,
                chat_type=chat_type,
                telegram_user_id=user_id,
                text=text,
            )
        )
    )


def make_adapter(world_engine, uow_factory, admin_chat_id: int) -> TelegramAdapter:
    return TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=object(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
        admin_chat_id=admin_chat_id,
    )


def test_non_admin_cannot_access_admin_chat_and_chat_creates_no_instance(
    world_engine, uow_factory, monkeypatch
) -> None:
    admin_chat_id = -9930
    before_instances = tuple(world_engine.list_instances())
    instance_resolver = GroupInstanceResolver(world_engine, uow_factory)

    def forbidden_resolve(*_args, **_kwargs):
        raise AssertionError("admin-chat updates must bypass game-instance resolution")

    monkeypatch.setattr(instance_resolver, "resolve", forbidden_resolve)
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=object(),
        instance_resolver=instance_resolver,
        admin_chat_id=admin_chat_id,
    )
    response = send(
        adapter,
        chat_id=admin_chat_id,
        chat_type="group",
        user_id=9930,
        text="/admin worlds",
    )

    assert tuple(world_engine.list_instances()) == before_instances
    with uow_factory() as uow:
        assert uow.chat_bindings.get_by_telegram_chat_id(admin_chat_id) is None
    assert response == "Доступ запрещён."


def test_admin_command_in_game_group_is_not_executed_or_bound(
    world_engine, uow_factory
) -> None:
    admin_chat_id = -9931
    game_chat_id = -9932
    before_instances = tuple(world_engine.list_instances())
    response = send(
        make_adapter(world_engine, uow_factory, admin_chat_id),
        chat_id=game_chat_id,
        chat_type="group",
        user_id=9932,
        text="/admin worlds",
    )

    assert response == "Команда не найдена."
    assert tuple(world_engine.list_instances()) == before_instances
    with uow_factory() as uow:
        assert uow.chat_bindings.get_by_telegram_chat_id(game_chat_id) is None


def test_admin_read_commands_do_not_change_world_state(world_engine, uow_factory) -> None:
    admin_chat_id = -9933
    admin_user_id = 9933
    world = world_engine.create_instance(telegram_chat_id=-9934, seed=34)
    character = world_engine.create_character(
        world.id,
        player_id="9934",
        name="Safety Subject",
        location_key=LocationKey("base"),
    )
    assert character.ok
    npc = world_engine.get_npcs(world.id)[0]
    with uow_factory() as uow:
        uow.admin_users.add(
            AdminUser(
                telegram_user_id=admin_user_id,
                name="Safety Admin",
                added_by_telegram_id=0,
                added_at=datetime.now(timezone.utc),
                active=True,
            )
        )
        uow.commit()

    instance_before = world_engine.get_instance(world.id)
    events_before = tuple(world_engine.get_events(world.id))
    instances_before = tuple(world_engine.list_instances())
    character_before = world_engine.get_character(
        world.id, CharacterId(character.payload["character_id"])
    )
    adapter = make_adapter(world_engine, uow_factory, admin_chat_id)
    responses = (
        send(
            adapter,
            chat_id=admin_chat_id,
            chat_type="supergroup",
            user_id=admin_user_id,
            text=f"/admin instance {world.id}",
        ),
        send(
            adapter,
            chat_id=admin_chat_id,
            chat_type="supergroup",
            user_id=admin_user_id,
            text=f"/admin events {world.id} 5",
        ),
        send(
            adapter,
            chat_id=admin_chat_id,
            chat_type="supergroup",
            user_id=admin_user_id,
            text=f"/admin character {world.id} {character.payload['character_id']}",
        ),
        send(
            adapter,
            chat_id=admin_chat_id,
            chat_type="supergroup",
            user_id=admin_user_id,
            text=f"/admin npc {world.id} {npc.id}",
        ),
        send(
            adapter,
            chat_id=admin_chat_id,
            chat_type="supergroup",
            user_id=admin_user_id,
            text=f"/admin location {world.id} base",
        ),
    )

    assert all(response for response in responses)
    instance_after = world_engine.get_instance(world.id)
    assert instance_after.state == instance_before.state
    assert instance_after.lifecycle == instance_before.lifecycle
    assert tuple(world_engine.get_events(world.id)) == events_before
    assert tuple(world_engine.list_instances()) == instances_before
    assert world_engine.get_character(
        world.id, CharacterId(character.payload["character_id"])
    ) == character_before
    with uow_factory() as uow:
        assert uow.chat_bindings.get_by_telegram_chat_id(admin_chat_id) is None
