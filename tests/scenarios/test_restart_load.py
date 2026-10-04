"""Scenario: мир переживает перезапуск процесса.

Каждый шаг сценария выполняется в отдельном процессе Python (см. фикстуры
``cli`` и ``alembic_upgrade`` в tests/conftest.py): состояние и журнал событий
не должны зависеть от жизни текущего процесса.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

CHAT_ID = "-1001"
SEED = "42"

CliRunner = Callable[..., subprocess.CompletedProcess[str]]


def _value(output: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}=(.+)$", output, re.MULTILINE)
    assert match is not None, f"в выводе нет {key}:\n{output}"
    return match.group(1).strip()


def test_state_and_event_log_survive_process_restart(
    tmp_path: Path,
    cli: CliRunner,
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'restart.db').as_posix()}"

    # Шаг 1: чистая БД + миграция (отдельный процесс).
    upgrade = alembic_upgrade(db_url)
    assert upgrade.returncode == 0, upgrade.stderr

    # Шаг 2: создание инстанса (отдельный процесс).
    created = cli(db_url, "create-world", "--chat-id", CHAT_ID, "--seed", SEED, "--environment", "TEST")
    assert created.returncode == 0, created.stderr
    instance_id = _value(created.stdout, "instance_id")
    assert _value(created.stdout, "telegram_chat_id") == CHAT_ID
    assert _value(created.stdout, "seed") == SEED
    assert _value(created.stdout, "lifecycle") == "ACTIVE"
    assert _value(created.stdout, "world_tick") == "0"
    # Правило A: у созданного инстанса state_version = 0.
    assert _value(created.stdout, "state_version") == "0"

    # Шаг 3: два изменения состояния — каждое в своём процессе.
    for attempt in range(2):
        tick = cli(db_url, "advance-tick", instance_id, "--cause", f"restart-{attempt}")
        assert tick.returncode == 0, tick.stderr
    assert _value(tick.stdout, "world_tick") == "2"
    assert _value(tick.stdout, "state_version") == "2"

    # Шаг 4: новый процесс читает изменённый мир.
    shown = cli(db_url, "show-world", instance_id)
    assert shown.returncode == 0, shown.stderr
    assert _value(shown.stdout, "instance_id") == instance_id
    assert _value(shown.stdout, "lifecycle") == "ACTIVE"
    assert _value(shown.stdout, "world_tick") == "2"
    assert _value(shown.stdout, "state_version") == "2"

    # Шаг 5: журнал событий восстановлен целиком и в правильном порядке.
    events = cli(db_url, "events", instance_id)
    assert events.returncode == 0, events.stderr
    assert _value(events.stdout, "events_total") == "3"
    assert events.stdout.count("EVENT ") == 3
    assert events.stdout.index("WORLD_INSTANCE_CREATED") < events.stdout.index("WORLD_TICK_ADVANCED")
    assert events.stdout.count("WORLD_TICK_ADVANCED") == 2
