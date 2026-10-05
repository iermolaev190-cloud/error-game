from world_error.domain.shared.kernel import WorldInstanceId
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


def test_resolve_existing_group_binding(world_engine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9101, seed=91)
    resolver = GroupInstanceResolver(world_engine, uow_factory)

    resolved = resolver.resolve(
        -9101,
        chat_type="supergroup",
        create_if_missing=False,
    )

    assert resolved == instance.id
    assert resolved != WorldInstanceId(str(-9101))


def test_first_group_message_creates_instance_and_binding(world_engine, uow_factory) -> None:
    resolver = GroupInstanceResolver(world_engine, uow_factory)

    resolved = resolver.resolve(
        -9102,
        chat_type="group",
        create_if_missing=True,
    )

    assert resolved is not None
    assert resolved != WorldInstanceId(str(-9102))
    with uow_factory() as uow:
        binding = uow.chat_bindings.get_by_telegram_chat_id(-9102)
    assert binding is not None
    assert binding.world_instance_id == resolved


def test_unknown_group_without_bootstrap_returns_none(world_engine, uow_factory) -> None:
    resolver = GroupInstanceResolver(world_engine, uow_factory)

    assert (
        resolver.resolve(
            -9103,
            chat_type="group",
            create_if_missing=False,
        )
        is None
    )


def test_non_group_chat_is_never_resolved_or_created(world_engine, uow_factory) -> None:
    resolver = GroupInstanceResolver(world_engine, uow_factory)

    assert (
        resolver.resolve(
            12345,
            chat_type="private",
            create_if_missing=True,
        )
        is None
    )
