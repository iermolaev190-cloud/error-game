from world_error.application.ai.key_resolver import InstanceKeyResolver
from world_error.domain.items.item import ItemOwnerType
from world_error.domain.shared.kernel import CharacterId, LocationKey


def test_resolves_location_items_npcs_and_characters_in_instance(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9911, seed=11)
    created = world_engine.create_character(
        instance.id,
        player_id="9911",
        name="Alice",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    resolver = InstanceKeyResolver(uow_factory)

    assert resolver.resolve_location_item(
        instance.id, LocationKey("base"), "medkit"
    ) is not None
    assert resolver.resolve_npc(instance.id, LocationKey("base"), "caretaker") is not None
    assert resolver.resolve_character(instance.id, LocationKey("base"), "alice") == character_id


def test_resolves_cyrillic_character_name(world_engine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9921, seed=21)
    created = world_engine.create_character(
        instance.id,
        player_id="9921",
        name="Иван Петров",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])

    resolved = InstanceKeyResolver(uow_factory).resolve_character(
        instance.id,
        LocationKey("base"),
        "иван_петров",
    )

    assert resolved == character_id


def test_resolves_inventory_items_by_character_and_instance(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9912, seed=12)
    created = world_engine.create_character(
        instance.id,
        player_id="9912",
        name="Alice",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    resolver = InstanceKeyResolver(uow_factory)

    assert resolver.resolve_inventory_item(instance.id, character_id, "medkit") is None
    with uow_factory() as uow:
        item = next(
            item
            for item in uow.items.list_at_location(instance.id, LocationKey("base"))
            if item.key == "medkit"
        )
        item.owner_type = ItemOwnerType.CHARACTER
        item.owner_id = str(character_id)
        item.location_key = None
        uow.items.save(item)
        uow.commit()

    assert resolver.resolve_inventory_item(instance.id, character_id, "medkit") == item.id


def test_resolves_requested_trade_item_from_counterparty_inventory(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9916, seed=16)
    initiator = world_engine.create_character(
        instance.id,
        player_id="9916",
        name="Initiator",
        location_key=LocationKey("base"),
    )
    counterparty = world_engine.create_character(
        instance.id,
        player_id="9917",
        name="Counterparty",
        location_key=LocationKey("base"),
    )
    assert initiator.ok and counterparty.ok
    initiator_id = CharacterId(initiator.payload["character_id"])
    counterparty_id = CharacterId(counterparty.payload["character_id"])
    with uow_factory() as uow:
        item = next(
            item
            for item in uow.items.list_at_location(instance.id, LocationKey("base"))
            if item.key == "medkit"
        )
        item.owner_type = ItemOwnerType.CHARACTER
        item.owner_id = str(counterparty_id)
        item.location_key = None
        uow.items.save(item)
        uow.commit()

    resolver = InstanceKeyResolver(uow_factory)
    assert resolver.resolve_inventory_item(instance.id, initiator_id, "medkit") is None
    assert resolver.resolve_inventory_item(instance.id, counterparty_id, "medkit") == item.id


def test_resolves_only_information_known_by_character_in_instance(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9917, seed=17)
    foreign = world_engine.create_instance(telegram_chat_id=-9918, seed=18)
    created = world_engine.create_character(
        instance.id,
        player_id="9918",
        name="Alice",
        location_key=LocationKey("base"),
    )
    foreign_created = world_engine.create_character(
        foreign.id,
        player_id="9919",
        name="Foreign Alice",
        location_key=LocationKey("base"),
    )
    assert created.ok and foreign_created.ok
    character_id = CharacterId(created.payload["character_id"])
    foreign_character_id = CharacterId(foreign_created.payload["character_id"])
    resolver = InstanceKeyResolver(uow_factory)

    assert resolver.resolve_known_information(instance.id, character_id, "dispatch_log") is None
    assert world_engine.inspect_information(
        foreign.id, character_id=foreign_character_id, target_key="dispatch_log"
    ).ok
    assert resolver.resolve_known_information(instance.id, character_id, "dispatch_log") is None
    assert world_engine.inspect_information(
        instance.id, character_id=character_id, target_key="dispatch_log"
    ).ok
    assert (
        resolver.resolve_known_information(instance.id, character_id, "DISPATCH_LOG")
        == "dispatch_log"
    )


def test_resolves_npc_for_friendly_transfer_error_within_instance(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9919, seed=19)
    foreign = world_engine.create_instance(telegram_chat_id=-9920, seed=20)
    resolver = InstanceKeyResolver(uow_factory)

    assert resolver.resolve_npc_in_instance(instance.id, "scout") is not None
    assert resolver.resolve_npc_in_instance(instance.id, "missing_npc") is None
    assert resolver.resolve_npc_in_instance(foreign.id, "scout") is not None
    assert resolver.resolve_npc_in_instance(instance.id, "caretaker") != (
        resolver.resolve_npc_in_instance(foreign.id, "caretaker")
    )


def test_item_resolution_is_scoped_to_requested_instance(
    world_engine, uow_factory
) -> None:
    selected = world_engine.create_instance(telegram_chat_id=-9913, seed=13)
    foreign = world_engine.create_instance(telegram_chat_id=-9914, seed=14)
    with uow_factory() as uow:
        selected_item = next(
            item
            for item in uow.items.list_at_location(selected.id, LocationKey("base"))
            if item.key == "medkit"
        )
        foreign_item = next(
            item
            for item in uow.items.list_at_location(foreign.id, LocationKey("base"))
            if item.key == "medkit"
        )

    resolved = InstanceKeyResolver(uow_factory).resolve_location_item(
        selected.id, LocationKey("base"), "medkit"
    )

    assert resolved == selected_item.id
    assert resolved != foreign_item.id


def test_missing_or_nonlocal_keys_do_not_resolve(world_engine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9915, seed=15)
    resolver = InstanceKeyResolver(uow_factory)

    assert resolver.resolve_location_item(
        instance.id, LocationKey("base"), "not_an_item"
    ) is None
    assert resolver.resolve_npc(instance.id, LocationKey("forest"), "caretaker") is None
    assert resolver.resolve_character(
        instance.id, LocationKey("base"), "not_a_character"
    ) is None
