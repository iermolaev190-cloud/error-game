from datetime import datetime, timezone

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def test_0011_backfills_existing_world_instances(db_url, monkeypatch) -> None:
    monkeypatch.setenv("WORLD_ERROR_DB_URL", db_url)
    config = Config("alembic.ini")
    command.upgrade(config, "0010_investigation_engine")

    connection = create_engine(db_url)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with connection.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO world_instances "
                    "(id, telegram_chat_id, seed, content_version, environment, lifecycle, "
                    "current_time, anchor_real_time, time_scale, world_tick, state_version, created_at) "
                    "VALUES (:id, :chat_id, :seed, :content_version, :environment, :lifecycle, "
                    ":current_time, :anchor_real_time, :time_scale, :world_tick, :state_version, :created_at)"
                ),
                {
                    "id": "wi_before_0011",
                    "chat_id": -9401,
                    "seed": 94,
                    "content_version": "v1",
                    "environment": "DEV",
                    "lifecycle": "ACTIVE",
                    "current_time": now,
                    "anchor_real_time": now,
                    "time_scale": 1.0,
                    "world_tick": 0,
                    "state_version": 0,
                    "created_at": now,
                },
            )
        command.upgrade(config, "head")
        with connection.connect() as conn:
            binding = conn.execute(
                text(
                    "SELECT telegram_chat_id, world_instance_id "
                    "FROM chat_bindings WHERE telegram_chat_id = :chat_id"
                ),
                {"chat_id": -9401},
            ).one()
        assert binding == (-9401, "wi_before_0011")
    finally:
        connection.dispose()
