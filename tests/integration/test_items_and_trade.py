"""Integration: finite item ownership, atomic transfer, and instance isolation."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Callable

import pytest
from sqlalchemy.exc import IntegrityError

from world_error.application.commands._item_transfer import ItemTransferWorkspace
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import Event, EventType
from world_error.domain.items.item import Item, ItemOwnerType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    EventId,
    ItemId,
    LocationKey,
    WorldInstanceId,
    new_item_id,
)
from world_error.domain.world.instance import WorldInstance
from world_error.infrastructure.db.repositories.event_log import SqlEventLogRepository
from world_error.infrastructure.db.tables import items
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
BASE = LocationKey("base")


def make_world(world_engine: WorldEngine, chat_id: int = -1001) -> WorldInstance:
    return world_engine.create_instance(telegram_chat_id=chat_id, seed=42)


def make_character(world_engine: WorldEngine, instance: WorldInstance, name: str) -> CharacterId:
    result = world_engine.create_character(instance.id, player_id=name, name=name)
    assert result.ok is True, result.error
    return CharacterId(result.payload["character_id"])


def seed_character_item(
    *, uow_factory: Callable[[], SqlAlchemyUnitOfWork], catalog, world_id: WorldInstanceId,
    character_id: CharacterId, key: str, quantity: int, item_id: str,
) -> ItemId:
    item = Item.create(
        id=ItemId(item_id),
        world_instance_id=world_id,
        definition=catalog.item_definition(key),
        owner_type=ItemOwnerType.CHARACTER,
        owner_id=str(character_id),
        location_key=None,
        quantity=quantity,
        now=NOW,
    )
    with uow_factory() as uow:
        uow.items.add(item)
        uow.commit()
    return item.id


def test_take_and_drop_transfer_one_item_through_events(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = make_world(world_engine)
    character_id = make_character(world_engine, instance, "player-a")
    with uow_factory() as uow:
        medkit = next(
            item
            for item in uow.items.list_at_location(instance.id, BASE)
            if item.key == "medkit"
        )

    taken = world_engine.take_item(instance.id, character_id=character_id, item_id=medkit.id)
    assert taken.ok is True, taken.error
    assert taken.payload["destination_item_id"] == str(medkit.id)
    assert [item.key for item in world_engine.get_inventory(instance.id, character_id).items] == [
        "medkit"
    ]

    dropped = world_engine.drop_item(instance.id, character_id=character_id, item_id=medkit.id)
    assert dropped.ok is True, dropped.error
    with uow_factory() as uow:
        returned = uow.items.get(instance.id, medkit.id)
    assert returned.owner_type is ItemOwnerType.LOCATION
    assert returned.owner_id is None
    assert returned.location_key == BASE
    item_events = [
        event.type
        for event in world_engine.get_events(instance.id)
        if event.type in (EventType.ITEM_TAKEN, EventType.ITEM_DROPPED)
    ]
    assert item_events == [EventType.ITEM_TAKEN, EventType.ITEM_DROPPED]


def test_trade_partially_transfers_and_merges_credits_stack(
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    catalog,
) -> None:
    instance = make_world(world_engine)
    initiator = make_character(world_engine, instance, "player-a")
    counterparty = make_character(world_engine, instance, "player-b")
    credits_a = seed_character_item(
        uow_factory=uow_factory,
        catalog=catalog,
        world_id=instance.id,
        character_id=initiator,
        key="credits",
        quantity=5,
        item_id="itm_credits_a",
    )
    credits_b = seed_character_item(
        uow_factory=uow_factory,
        catalog=catalog,
        world_id=instance.id,
        character_id=counterparty,
        key="credits",
        quantity=2,
        item_id="itm_credits_b",
    )
    medkit_b = seed_character_item(
        uow_factory=uow_factory,
        catalog=catalog,
        world_id=instance.id,
        character_id=counterparty,
        key="medkit",
        quantity=1,
        item_id="itm_medkit_b",
    )
    events_before = len(world_engine.get_events(instance.id))

    result = world_engine.trade_items(
        instance.id,
        initiator_id=initiator,
        counterparty_id=counterparty,
        offered_item_id=credits_a,
        offered_quantity=3,
        requested_item_id=medkit_b,
    )

    assert result.ok is True, result.error
    assert result.payload["offered_merged_into_existing"] is True
    assert len(world_engine.get_events(instance.id)) == events_before + 1
    trade_event = world_engine.get_events(instance.id)[-1]
    assert trade_event.type is EventType.ITEM_TRANSFERRED
    assert trade_event.payload["transfers"] == [
        {
            "source_item_id": str(medkit_b),
            "destination_item_id": str(medkit_b),
            "quantity": 1,
            "merged_into_existing": False,
        },
        {
            "source_item_id": str(credits_a),
            "destination_item_id": str(credits_b),
            "quantity": 3,
            "merged_into_existing": True,
        },
    ]

    inventory_a = world_engine.get_inventory(instance.id, initiator).items
    inventory_b = world_engine.get_inventory(instance.id, counterparty).items
    assert {(item.key, item.quantity) for item in inventory_a} == {("credits", 2), ("medkit", 1)}
    assert [(item.key, item.quantity) for item in inventory_b] == [("credits", 5)]
    assert sum(item.quantity for item in (*inventory_a, *inventory_b) if item.key == "credits") == 7


def test_trade_requires_colocation_and_rejects_dead_counterparty(world_engine: WorldEngine) -> None:
    instance = make_world(world_engine)
    initiator = make_character(world_engine, instance, "player-a")
    counterparty = make_character(world_engine, instance, "player-b")
    assert world_engine.move_character(
        instance.id, character_id=counterparty, to_location_key=LocationKey("forest")
    ).ok is True

    separated = world_engine.trade_items(
        instance.id,
        initiator_id=initiator,
        counterparty_id=counterparty,
        offered_item_id=ItemId("itm_missing"),
    )
    assert separated.ok is False
    assert separated.error is not None and separated.error.code is ErrorCode.NOT_ALLOWED

    assert world_engine.move_character(
        instance.id, character_id=counterparty, to_location_key=BASE
    ).ok is True
    cause_event_id = world_engine.get_events(instance.id)[-1].id
    assert world_engine.kill_character(
        instance.id, counterparty, cause_event_id=cause_event_id
    ).ok is True
    dead = world_engine.trade_items(
        instance.id,
        initiator_id=initiator,
        counterparty_id=counterparty,
        offered_item_id=ItemId("itm_missing"),
    )
    assert dead.ok is False
    assert dead.error is not None and dead.error.code is ErrorCode.NOT_ALLOWED


def test_item_queries_are_scoped_to_world_instance(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork], catalog
) -> None:
    world_a = make_world(world_engine, chat_id=-1101)
    world_b = make_world(world_engine, chat_id=-1102)
    character_a = make_character(world_engine, world_a, "player-a")
    character_b = make_character(world_engine, world_b, "player-b")
    item_id = seed_character_item(
        uow_factory=uow_factory,
        catalog=catalog,
        world_id=world_a.id,
        character_id=character_a,
        key="medkit",
        quantity=1,
        item_id="itm_isolated",
    )

    with uow_factory() as uow:
        with pytest.raises(DomainError) as exc_info:
            uow.items.get(world_b.id, item_id)
        assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert world_engine.get_inventory(world_b.id, character_b).items == ()


def test_database_rejects_item_owned_by_character_from_another_instance(
    world_engine: WorldEngine, engine
) -> None:  # noqa: ANN001
    world_a = make_world(world_engine, chat_id=-1103)
    world_b = make_world(world_engine, chat_id=-1104)
    foreign_character = make_character(world_engine, world_b, "player-b")

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                items.insert().values(
                    id="itm_cross_world_owner",
                    world_instance_id=str(world_a.id),
                    key="medkit",
                    owner_type="CHARACTER",
                    owner_id=str(foreign_character),
                    location_key=None,
                    quantity=1,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )


def test_inventory_is_owner_scoped_and_has_no_owner_fields(world_engine: WorldEngine) -> None:
    import dataclasses

    from world_error.application.queries.inventory_view import InventoryItemView

    instance = make_world(world_engine)
    first = make_character(world_engine, instance, "player-a")
    second = make_character(world_engine, instance, "player-b")
    assert world_engine.get_inventory(instance.id, first).items == ()
    assert world_engine.get_inventory(instance.id, second).items == ()
    assert {field.name for field in dataclasses.fields(InventoryItemView)} == {
        "item_id",
        "key",
        "name",
        "description",
        "type",
        "weight",
        "quantity",
    }


def test_item_event_idempotency_is_per_instance(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork], catalog
) -> None:
    first_engine = WorldEngine(uow_factory=uow_factory, catalog=catalog)
    instance = make_world(first_engine)
    character = make_character(first_engine, instance, "player-a")
    with uow_factory() as uow:
        medkit = next(
            item
            for item in uow.items.list_at_location(instance.id, BASE)
            if item.key == "medkit"
        )
    stable_event_id = EventId("ev_take_idempotency")
    replay_engine = WorldEngine(
        uow_factory=uow_factory,
        catalog=catalog,
        new_event_id_factory=lambda: stable_event_id,
    )
    first = replay_engine.take_item(instance.id, character_id=character, item_id=medkit.id)
    event_count = len(first_engine.get_events(instance.id))
    replay = replay_engine.take_item(instance.id, character_id=character, item_id=medkit.id)

    assert first.ok is True
    assert replay.ok is False
    assert replay.error is not None and replay.error.code is ErrorCode.ALREADY_PROCESSED
    assert len(first_engine.get_events(instance.id)) == event_count


def test_trade_event_append_failure_rolls_back_money_and_item(
    monkeypatch: pytest.MonkeyPatch,
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    catalog,
) -> None:
    instance = make_world(world_engine)
    initiator = make_character(world_engine, instance, "player-a")
    counterparty = make_character(world_engine, instance, "player-b")
    credits = seed_character_item(
        uow_factory=uow_factory,
        catalog=catalog,
        world_id=instance.id,
        character_id=initiator,
        key="credits",
        quantity=5,
        item_id="itm_rollback_credits",
    )
    medkit = seed_character_item(
        uow_factory=uow_factory,
        catalog=catalog,
        world_id=instance.id,
        character_id=counterparty,
        key="medkit",
        quantity=1,
        item_id="itm_rollback_medkit",
    )
    state_before = world_engine.get_instance(instance.id).state
    event_count_before = len(world_engine.get_events(instance.id))
    original_append = SqlEventLogRepository.append

    def fail_transfer_append(repository, event: Event) -> None:  # noqa: ANN001
        if event.type is EventType.ITEM_TRANSFERRED:
            raise DomainError(ErrorCode.ALREADY_PROCESSED, "injected event append failure")
        original_append(repository, event)

    monkeypatch.setattr(SqlEventLogRepository, "append", fail_transfer_append)
    result = world_engine.trade_items(
        instance.id,
        initiator_id=initiator,
        counterparty_id=counterparty,
        offered_item_id=credits,
        offered_quantity=2,
        requested_item_id=medkit,
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.ALREADY_PROCESSED
    assert [(item.key, item.quantity) for item in world_engine.get_inventory(instance.id, initiator).items] == [
        ("credits", 5)
    ]
    assert [(item.key, item.quantity) for item in world_engine.get_inventory(instance.id, counterparty).items] == [
        ("medkit", 1)
    ]
    assert not any(
        event.type is EventType.ITEM_TRANSFERRED for event in world_engine.get_events(instance.id)
    )
    state_after = world_engine.get_instance(instance.id).state
    assert (state_after.world_tick, state_after.state_version) == (
        state_before.world_tick,
        state_before.state_version,
    )
    assert len(world_engine.get_events(instance.id)) == event_count_before


def test_dead_character_keeps_items_and_new_character_does_not_inherit(
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    catalog,
) -> None:
    instance = make_world(world_engine)
    previous = make_character(world_engine, instance, "player-a")
    item_id = seed_character_item(
        uow_factory=uow_factory,
        catalog=catalog,
        world_id=instance.id,
        character_id=previous,
        key="medkit",
        quantity=1,
        item_id="itm_death_kept",
    )
    cause_event_id = world_engine.get_events(instance.id)[-1].id
    death = world_engine.kill_character(instance.id, previous, cause_event_id=cause_event_id)
    assert death.ok is True

    spawned = world_engine.spawn_new_character(instance.id, player_id="player-a", name="New")
    assert spawned.ok is True, spawned.error
    new_character = CharacterId(spawned.payload["character_id"])
    assert [item.item_id for item in world_engine.get_inventory(instance.id, previous).items] == [
        str(item_id)
    ]
    assert world_engine.get_inventory(instance.id, new_character).items == ()


def test_items_and_trade_survive_cli_process_restarts(
    cli: Callable[..., subprocess.CompletedProcess[str]],
    db_url: str,
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    instance = make_world(world_engine, chat_id=-1110)
    initiator = make_character(world_engine, instance, "player-a")
    counterparty = make_character(world_engine, instance, "player-b")
    with uow_factory() as uow:
        base_items = uow.items.list_at_location(instance.id, BASE)
    credits = next(item for item in base_items if item.key == "credits")
    medkit = next(item for item in base_items if item.key == "medkit")

    shown_location = cli(
        db_url,
        "show-location",
        "--world-id", str(instance.id),
        "--character-id", str(initiator),
        "--location", str(BASE),
    )
    assert shown_location.returncode == 0, shown_location.stderr
    assert "ITEM credits Кредиты" in shown_location.stdout
    assert "ITEM medkit Аптечка" in shown_location.stdout
    assert str(credits.id) not in shown_location.stdout
    assert "owner_id" not in shown_location.stdout

    take_credits = cli(
        db_url,
        "take",
        "--world-id", str(instance.id),
        "--character-id", str(initiator),
        "--item-id", str(credits.id),
    )
    take_medkit = cli(
        db_url,
        "take",
        "--world-id", str(instance.id),
        "--character-id", str(counterparty),
        "--item-id", str(medkit.id),
    )
    assert take_credits.returncode == 0, take_credits.stderr
    assert take_medkit.returncode == 0, take_medkit.stderr

    trade = cli(
        db_url,
        "trade",
        "--world-id", str(instance.id),
        "--character-id", str(initiator),
        "--to-character-id", str(counterparty),
        "--offer-item-id", str(credits.id),
        "--request-item-id", str(medkit.id),
    )
    assert trade.returncode == 0, trade.stderr

    shown_a = cli(
        db_url,
        "show-inventory",
        "--world-id", str(instance.id),
        "--character-id", str(initiator),
    )
    shown_b = cli(
        db_url,
        "show-inventory",
        "--world-id", str(instance.id),
        "--character-id", str(counterparty),
    )
    assert shown_a.returncode == shown_b.returncode == 0
    assert "ITEM medkit Аптечка quantity=1" in shown_a.stdout
    assert "ITEM credits Кредиты quantity=1" in shown_b.stdout
    assert str(counterparty) not in shown_a.stdout
    assert str(initiator) not in shown_b.stdout


def test_two_stale_take_transactions_cannot_duplicate_a_location_item(
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    catalog,
) -> None:
    instance = make_world(world_engine)
    first_character = make_character(world_engine, instance, "player-a")
    second_character = make_character(world_engine, instance, "player-b")
    with uow_factory() as seed_uow:
        source_item = next(
            item
            for item in seed_uow.items.list_at_location(instance.id, BASE)
            if item.key == "medkit"
        )

    with uow_factory() as first_uow, uow_factory() as second_uow:
        first_instance = first_uow.world_instances.get(instance.id)
        second_instance = second_uow.world_instances.get(instance.id)
        first_expected = first_instance.state.state_version
        second_expected = second_instance.state.state_version
        first_item = first_uow.items.get(instance.id, source_item.id)
        second_item = second_uow.items.get(instance.id, source_item.id)
        first_workspace = ItemTransferWorkspace(
            catalog=catalog,
            now=NOW,
            new_item_id=new_item_id,
            existing_items=(first_item,),
        )
        first_workspace.transfer(
            item_id=first_item.id,
            quantity=1,
            owner_type=ItemOwnerType.CHARACTER,
            owner_id=str(first_character),
            location_key=None,
        )
        first_event = Event(
            id=EventId("ev_racing_take_a"),
            world_instance_id=instance.id,
            type=EventType.ITEM_TAKEN,
            created_at=NOW,
            executed_at=NOW,
            actor=str(first_character),
            payload={**first_workspace.event_payload(), "character_id": str(first_character)},
        )

        second_workspace = ItemTransferWorkspace(
            catalog=catalog,
            now=NOW,
            new_item_id=new_item_id,
            existing_items=(second_item,),
        )
        second_workspace.transfer(
            item_id=second_item.id,
            quantity=1,
            owner_type=ItemOwnerType.CHARACTER,
            owner_id=str(second_character),
            location_key=None,
        )
        second_event = Event(
            id=EventId("ev_racing_take_b"),
            world_instance_id=instance.id,
            type=EventType.ITEM_TAKEN,
            created_at=NOW,
            executed_at=NOW,
            actor=str(second_character),
            payload={**second_workspace.event_payload(), "character_id": str(second_character)},
        )

        first_workspace.persist(
            uow=first_uow,
            instance=first_instance,
            expected_state_version=first_expected,
            event=first_event,
        )
        with pytest.raises(DomainError) as exc_info:
            second_workspace.persist(
                uow=second_uow,
                instance=second_instance,
                expected_state_version=second_expected,
                event=second_event,
            )
        assert exc_info.value.code is ErrorCode.CONFLICT
        second_uow.rollback()

    with uow_factory() as uow:
        persisted = uow.items.get(instance.id, source_item.id)
    assert persisted.owner_type is ItemOwnerType.CHARACTER
    assert persisted.owner_id == str(first_character)
    item_taken_events = [
        event for event in world_engine.get_events(instance.id) if event.type is EventType.ITEM_TAKEN
    ]
    assert [event.id for event in item_taken_events] == [EventId("ev_racing_take_a")]