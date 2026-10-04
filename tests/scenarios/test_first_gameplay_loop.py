"""Scenario: первый игровой цикл переживает перезапуск процесса.

CREATE WORLD INSTANCE → CREATE CHARACTER → MOVE base→forest → MOVE forest→old_station
→ INSPECT damaged_radio → Information (мир) + Knowledge (персонаж)
→ RESTART ПРОЦЕССА → тот же персонаж, локация, знание и журнал событий.

Каждый шаг — отдельный процесс Python (фикстуры ``cli``/``alembic_upgrade``),
поэтому никакое состояние не может сохраниться в памяти процесса.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

CHAT_ID = "-1001"
PLAYER_ID = "player-1"
NAME = "Аня"
CLAIM_FRAGMENT = "корпус вскрыт"
TRUTH_FRAGMENT = "намеренно"

CliRunner = Callable[..., subprocess.CompletedProcess[str]]


def _value(output: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}=(.+)$", output, re.MULTILINE)
    assert match is not None, f"в выводе нет {key}:\n{output}"
    return match.group(1).strip()


def test_first_gameplay_loop_survives_process_restart(
    tmp_path: Path,
    cli: CliRunner,
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'loop.db').as_posix()}"

    # Шаг 0: чистая БД + миграции (отдельный процесс).
    upgrade = alembic_upgrade(db_url)
    assert upgrade.returncode == 0, upgrade.stderr

    # Шаг 1: мир.
    created_world = cli(
        db_url, "create-world", "--chat-id", CHAT_ID, "--seed", "42", "--environment", "TEST"
    )
    assert created_world.returncode == 0, created_world.stderr
    world_id = _value(created_world.stdout, "instance_id")
    assert _value(created_world.stdout, "content_version") == "v1"
    assert _value(created_world.stdout, "state_version") == "0"
    assert _value(created_world.stdout, "world_tick") == "0"

    # Шаг 2: персонаж.
    created_character = cli(
        db_url,
        "create-character",
        "--world-id",
        world_id,
        "--player-id",
        PLAYER_ID,
        "--name",
        NAME,
    )
    assert created_character.returncode == 0, created_character.stderr
    character_id = _value(created_character.stdout, "character_id")
    assert _value(created_character.stdout, "location_key") == "base"
    assert _value(created_character.stdout, "lifecycle") == "ALIVE"
    assert _value(created_character.stdout, "activity") == "ACTIVE"
    assert _value(created_character.stdout, "state_version") == "1"

    # Шаг 3: перемещения base → forest → old_station.
    move_forest = cli(
        db_url, "move", "--world-id", world_id, "--character-id", character_id, "--to", "forest"
    )
    assert move_forest.returncode == 0, move_forest.stderr
    assert _value(move_forest.stdout, "from") == "base"
    assert _value(move_forest.stdout, "to") == "forest"
    assert _value(move_forest.stdout, "world_tick") == "2"

    move_station = cli(
        db_url,
        "move",
        "--world-id",
        world_id,
        "--character-id",
        character_id,
        "--to",
        "old_station",
    )
    assert move_station.returncode == 0, move_station.stderr
    assert _value(move_station.stdout, "to") == "old_station"
    assert _value(move_station.stdout, "world_tick") == "3"

    # Шаг 4: находка — Information в мире + Knowledge у персонажа.
    inspect = cli(
        db_url,
        "inspect",
        "--world-id",
        world_id,
        "--character-id",
        character_id,
        "--target",
        "damaged_radio",
    )
    assert inspect.returncode == 0, inspect.stderr
    assert _value(inspect.stdout, "already_known") == "False"
    assert _value(inspect.stdout, "claim_type") == "FACT"
    assert _value(inspect.stdout, "confidence") == "LIKELY"
    assert CLAIM_FRAGMENT in inspect.stdout
    assert _value(inspect.stdout, "state_version") == "4"

    # Шаг 5: RESTART — новые процессы читают изменённый мир.
    shown = cli(db_url, "show-character", "--world-id", world_id, "--character-id", character_id)
    assert shown.returncode == 0, shown.stderr
    assert _value(shown.stdout, "character_id") == character_id
    assert _value(shown.stdout, "player_id") == PLAYER_ID
    assert _value(shown.stdout, "name") == NAME
    assert _value(shown.stdout, "lifecycle") == "ALIVE"
    assert _value(shown.stdout, "activity") == "ACTIVE"
    assert _value(shown.stdout, "location_key") == "old_station"
    assert _value(shown.stdout, "knowledge_total") == "1"
    assert "KNOWLEDGE FACT LIKELY" in shown.stdout
    assert CLAIM_FRAGMENT in shown.stdout
    # Канонический факт в интерфейс не выводится.
    assert TRUTH_FRAGMENT not in shown.stdout

    # Шаг 6: журнал событий восстановлен целиком и в правильном порядке.
    events = cli(db_url, "events", world_id)
    assert events.returncode == 0, events.stderr
    assert _value(events.stdout, "events_total") == "5"
    assert events.stdout.index("WORLD_INSTANCE_CREATED") < events.stdout.index("CHARACTER_CREATED")
    assert events.stdout.index("CHARACTER_CREATED") < events.stdout.index("CHARACTER_MOVED")
    assert events.stdout.index("CHARACTER_MOVED") < events.stdout.index("INFORMATION_DISCOVERED")
    assert events.stdout.count("CHARACTER_MOVED") == 2
    assert events.stdout.count("INFORMATION_DISCOVERED") == 1

    # Повторный INSPECT после перезапуска — no-op без нового события.
    repeated = cli(
        db_url,
        "inspect",
        "--world-id",
        world_id,
        "--character-id",
        character_id,
        "--target",
        "damaged_radio",
    )
    assert repeated.returncode == 0, repeated.stderr
    assert _value(repeated.stdout, "already_known") == "True"
    events_after = cli(db_url, "events", world_id)
    assert _value(events_after.stdout, "events_total") == "5"
