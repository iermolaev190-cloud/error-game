import pytest

from world_error.domain.shared.kernel import DomainError, LocationKey
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


def add_player(world_engine, instance_id, player_id: str) -> None:
    result = world_engine.create_character(
        instance_id,
        player_id=player_id,
        name="DM Player",
        location_key=LocationKey("base"),
    )
    assert result.ok, result.error


def test_dm_instance_uses_last_group_binding(world_engine, uow_factory) -> None:
    first = world_engine.create_instance(telegram_chat_id=-9401, seed=94)
    second = world_engine.create_instance(telegram_chat_id=-9402, seed=95)
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    resolver.record_last_group_chat(941, -9402)

    assert resolver.resolve_dm_instance(941) == second.id
    assert resolver.resolve_dm_instance(941) != first.id


def test_dm_without_last_group_or_character_fails(world_engine, uow_factory) -> None:
    resolver = GroupInstanceResolver(world_engine, uow_factory)

    with pytest.raises(DomainError, match="Add the bot to a group"):
        resolver.resolve_dm_instance(942)


def test_dm_falls_back_to_single_active_character_instance(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9403, seed=96)
    add_player(world_engine, instance.id, "943")
    resolver = GroupInstanceResolver(world_engine, uow_factory)

    assert resolver.resolve_dm_instance(943) == instance.id


def test_dm_requires_group_choice_when_player_has_multiple_instances(
    world_engine, uow_factory
) -> None:
    first = world_engine.create_instance(telegram_chat_id=-9404, seed=97)
    second = world_engine.create_instance(telegram_chat_id=-9405, seed=98)
    add_player(world_engine, first.id, "944")
    add_player(world_engine, second.id, "944")
    resolver = GroupInstanceResolver(world_engine, uow_factory)

    with pytest.raises(DomainError, match="multiple worlds"):
        resolver.resolve_dm_instance(944)


def test_stale_last_group_does_not_fall_back_to_another_instance(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9406, seed=99)
    add_player(world_engine, instance.id, "945")
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    resolver.record_last_group_chat(945, -9499)

    with pytest.raises(DomainError, match="last group"):
        resolver.resolve_dm_instance(945)


def test_dm_character_is_scoped_to_user_and_instance(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9407, seed=100)
    add_player(world_engine, instance.id, "946")
    resolver = GroupInstanceResolver(world_engine, uow_factory)

    assert resolver.resolve_dm_character(947, instance.id) is None
    assert resolver.resolve_dm_character(946, instance.id) is not None
