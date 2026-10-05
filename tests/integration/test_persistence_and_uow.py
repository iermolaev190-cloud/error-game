"""Integration: миграция с нуля, round-trip состояния, атомарность Unit of Work."""

from __future__ import annotations

import subprocess
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    EventId,
    WorldInstanceId,
)
from world_error.domain.world.instance import (
    InstanceEnvironment,
    InstanceLifecycle,
    WorldInstance,
)
from world_error.infrastructure.db.engine import create_db_engine
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_alembic_upgrade_head_on_clean_database(
    tmp_path: Path, alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]]
) -> None:
    url = f"sqlite+pysqlite:///{(tmp_path / 'clean.db').as_posix()}"
    result = alembic_upgrade(url)
    assert result.returncode == 0, result.stderr

    db_engine = create_db_engine(url)
    try:
        inspector = inspect(db_engine)
        tables = set(inspector.get_table_names())
        character_columns = {column["name"] for column in inspector.get_columns("characters")}
        relationship_columns = {column["name"] for column in inspector.get_columns("relationships")}
        item_columns = {column["name"] for column in inspector.get_columns("items")}
        character_checks = {check["name"] for check in inspector.get_check_constraints("characters")}
        item_checks = {check["name"] for check in inspector.get_check_constraints("items")}
        item_foreign_keys = inspector.get_foreign_keys("items")
    finally:
        db_engine.dispose()

    assert {"world_instances", "events", "alembic_version"} <= tables
    # Миграция 0002 добавляет персонажей, локации, информацию и знание,
    # 0003 — NPC, 0004 — отношения, 0005 — последствия, 0006 — time,
    # 0007 — death references and legacy documents.
    assert {
        "characters",
        "location_states",
        "information",
        "knowledge",
        "npcs",
        "relationships",
        "scheduled_events",
        "consequences",
        "consequence_causes",
        "legacy_items",
        "factions",
        "faction_locations",
        "items",
    } <= tables
    assert "visibility" in relationship_columns
    assert {"owner_type", "owner_id", "location_key", "quantity"} <= item_columns
    assert {"ck_items_owner_type", "ck_items_positive_quantity", "ck_items_owner_shape"} <= item_checks
    item_fk_columns = {tuple(foreign_key["constrained_columns"]) for foreign_key in item_foreign_keys}
    assert ("world_instance_id", "location_key") in item_fk_columns
    assert ("world_instance_id", "owner_id") in item_fk_columns
    assert {"death_event_id", "death_cause_event_id"} <= character_columns
    assert "ck_characters_death_references" in character_checks


def test_relationship_visibility_migration_backfills_public(tmp_path: Path) -> None:
    db_path = tmp_path / "visibility-backfill.db"
    url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    repo_root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "WORLD_ERROR_DB_URL": url,
        "PYTHONPATH": str(repo_root / "src"),
        "PYTHONIOENCODING": "utf-8",
    }

    old_schema = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0007_death_action_cost"],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert old_schema.returncode == 0, old_schema.stderr

    db_engine = create_db_engine(url)
    try:
        with db_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO world_instances "
                    "(id, telegram_chat_id, seed, content_version, environment, lifecycle, "
                    "current_time, anchor_real_time, time_scale, world_tick, state_version, created_at) "
                    "VALUES ('wi_old', -1, 1, 'v1', 'TEST', 'ACTIVE', '2026-01-01 12:00:00', "
                    "'2026-01-01 12:00:00', 1.0, 0, 0, '2026-01-01 12:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO relationships "
                    "(id, world_instance_id, holder_type, holder_id, subject_type, subject_id, "
                    "kind, level, created_at, updated_at) "
                    "VALUES ('rel_old', 'wi_old', 'NPC', 'npc_old', 'CHARACTER', 'ch_old', "
                    "'TRUST', 'NEUTRAL', '2026-01-01 12:00:00', '2026-01-01 12:00:00')"
                )
            )
    finally:
        db_engine.dispose()

    upgraded = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert upgraded.returncode == 0, upgraded.stderr

    db_engine = create_db_engine(url)
    try:
        with db_engine.connect() as connection:
            visibility = connection.execute(
                text("SELECT visibility FROM relationships WHERE id = 'rel_old'")
            ).scalar_one()
    finally:
        db_engine.dispose()
    assert visibility == "PUBLIC"


def test_created_instance_is_loaded_from_new_session(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    created = world_engine.create_instance(
        telegram_chat_id=-1001, seed=42, environment=InstanceEnvironment.TEST
    )

    with uow_factory() as uow:
        loaded = uow.world_instances.get(created.id)

    assert loaded.id == created.id
    assert loaded.telegram_chat_id == -1001
    assert loaded.seed == 42
    assert loaded.environment is InstanceEnvironment.TEST
    assert loaded.lifecycle is InstanceLifecycle.ACTIVE
    assert (loaded.state.world_tick, loaded.state.state_version) == (0, 0)
    assert loaded.state.current_time == created.state.current_time


def test_state_and_event_log_are_persisted_in_order(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    world_engine.advance_tick(instance.id, cause="first")
    world_engine.advance_tick(instance.id, cause="second")

    loaded = world_engine.get_instance(instance.id)
    assert (loaded.state.world_tick, loaded.state.state_version) == (2, 2)

    events = list(world_engine.get_events(instance.id))
    assert [event.type for event in events] == [
        EventType.WORLD_INSTANCE_CREATED,
        EventType.WORLD_TICK_ADVANCED,
        EventType.WORLD_TICK_ADVANCED,
    ]
    assert [event.cause for event in events][1:] == ["first", "second"]
    assert all(event.world_instance_id == instance.id for event in events)


def test_status_change_goes_through_unit_of_work(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    world_engine.change_status(instance.id, to=InstanceLifecycle.PAUSED, cause="pause")

    loaded = world_engine.get_instance(instance.id)
    assert loaded.lifecycle is InstanceLifecycle.PAUSED
    assert loaded.state.state_version == 1

    last_event = list(world_engine.get_events(instance.id))[-1]
    assert last_event.type is EventType.WORLD_INSTANCE_STATUS_CHANGED
    assert dict(last_event.payload) == {"from": "ACTIVE", "to": "PAUSED"}
    assert last_event.cause == "pause"


def test_illegal_transition_leaves_no_trace(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    world_engine.change_status(instance.id, to=InstanceLifecycle.ARCHIVED)

    version_before = world_engine.get_instance(instance.id).state.state_version
    events_before = len(world_engine.get_events(instance.id))

    with pytest.raises(DomainError) as exc_info:
        world_engine.change_status(instance.id, to=InstanceLifecycle.ACTIVE)

    assert exc_info.value.code is ErrorCode.INVALID_ACTION
    assert world_engine.get_instance(instance.id).state.state_version == version_before
    assert len(world_engine.get_events(instance.id)) == events_before


def test_uow_rolls_back_state_and_event(uow_factory: Callable[[], SqlAlchemyUnitOfWork]) -> None:
    instance = WorldInstance.create(
        id=WorldInstanceId("wi_rollback"),
        telegram_chat_id=-1001,
        seed=42,
        content_version="v1",
        environment=InstanceEnvironment.TEST,
        now=NOW,
    )
    event = Event(
        id=EventId("ev_rollback"),
        world_instance_id=instance.id,
        type=EventType.WORLD_INSTANCE_CREATED,
        created_at=NOW,
        executed_at=NOW,
    )

    with pytest.raises(RuntimeError):
        with uow_factory() as uow:
            uow.world_instances.add(instance)
            uow.events.append(event)
            raise RuntimeError("boom")

    with uow_factory() as uow:
        with pytest.raises(DomainError) as exc_info:
            uow.world_instances.get(instance.id)
        assert exc_info.value.code is ErrorCode.NOT_FOUND
        assert list(uow.events.list_for_instance(instance.id)) == []
