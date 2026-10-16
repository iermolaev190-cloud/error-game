from sqlalchemy import create_engine, select

from world_error.infrastructure.db.tables import admin_users


def test_cli_bootstraps_admin_without_an_instance(db_url, cli, alembic_upgrade) -> None:
    migrated = alembic_upgrade(db_url)
    assert migrated.returncode == 0, migrated.stderr

    result = cli(
        db_url,
        "admin",
        "add-user",
        "--telegram-id",
        "9920",
        "--name",
        "Bootstrap Admin",
    )

    assert result.returncode == 0, result.stderr
    assert "admin_user=9920 active=true added_by=system" in result.stdout
    engine = create_engine(db_url)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                select(admin_users).where(admin_users.c.telegram_user_id == 9920)
            ).mappings().one()
    finally:
        engine.dispose()
    assert row["name"] == "Bootstrap Admin"
    assert row["added_by_telegram_id"] == 0
    assert row["active"] is True
