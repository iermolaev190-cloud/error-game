from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from world_error.domain.admin.admin_user import AdminUser


def test_admin_user_is_an_immutable_technical_record() -> None:
    added_at = datetime(2026, 10, 7, tzinfo=timezone.utc)
    admin = AdminUser(
        telegram_user_id=123,
        name="First Admin",
        added_by_telegram_id=0,
        added_at=added_at,
        active=True,
    )

    assert admin.telegram_user_id == 123
    assert admin.name == "First Admin"
    assert admin.added_by_telegram_id == 0
    assert admin.added_at is added_at
    assert admin.active
    with pytest.raises(FrozenInstanceError):
        admin.active = False  # type: ignore[misc]
