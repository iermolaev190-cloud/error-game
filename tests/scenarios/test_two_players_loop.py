"""Scenario: два игрока в одном мире — проекция локации и асимметрия знания.

Отдельные процессы: create world → два персонажа → оба MOVE до old_station
→ show-location от первого (публичные факты, без знания и truth)
→ INSPECT первым → show-location не меняет журнал → RESTART
→ у первого знание есть, у второго нет.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable

CHAT_ID = "-1001"
CLAIM_FRAGMENT = "корпус вскрыт"
TRUTH_FRAGMENT = "намеренно"

CliRunner = Callable[..., subprocess.CompletedProcess[str]]


def _value(output: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}=(.+)$", output, re.MULTILINE)
    assert match is not None, f"в выводе нет {key}:\n{output}"
    return match.group(1).strip()


def test_two_players_location_view_and_asymmetry_survive_restart(
    tmp_path: Path,
    cli: CliRunner,
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'two_players.db').as_posix()}"

    upgrade = alembic_upgrade(db_url)
    assert upgrade.returncode == 0, upgrade.stderr

    created_world = cli(
        db_url, "create-world", "--chat-id", CHAT_ID, "--seed", "42", "--environment", "TEST"
    )
    assert created_world.returncode == 0, created_world.stderr
    world_id = _value(created_world.stdout, "instance_id")

    characters = {}
    for player_id, name in (("player-a", "Аня"), ("player-b", "Борис")):
        created = cli(
            db_url,
            "create-character",
            "--world-id",
            world_id,
            "--player-id",
            player_id,
            "--name",
            name,
        )
        assert created.returncode == 0, created.stderr
        characters[player_id] = _value(created.stdout, "character_id")

    first = characters["player-a"]
    second = characters["player-b"]

    for character_id in (first, second):
        for target in ("forest", "old_station"):
            moved = cli(
                db_url,
                "move",
                "--world-id",
                world_id,
                "--character-id",
                character_id,
                "--to",
                target,
            )
            assert moved.returncode == 0, moved.stderr

    # Публичная проекция локации: оба игрока видны, знания и truth нет.
    view = cli(
        db_url,
        "show-location",
        "--world-id",
        world_id,
        "--character-id",
        first,
        "--location",
        "old_station",
    )
    assert view.returncode == 0, view.stderr
    assert _value(view.stdout, "location_key") == "old_station"
    assert _value(view.stdout, "name") == "Старая станция"
    assert _value(view.stdout, "discovery_state") == "DISCOVERED"
    assert _value(view.stdout, "characters_total") == "2"
    assert view.stdout.count("CHARACTER ") == 2
    assert first in view.stdout and second in view.stdout

    events_after_view = cli(db_url, "events", world_id)
    assert _value(events_after_view.stdout, "events_total") == "7"

    # Первый игрок находит улику; знание остаётся только у него.
    inspect = cli(
        db_url,
        "inspect",
        "--world-id",
        world_id,
        "--character-id",
        first,
        "--target",
        "damaged_radio",
    )
    assert inspect.returncode == 0, inspect.stderr
    assert _value(inspect.stdout, "state_version") == "7"

    # --- RESTART: новые процессы ---
    view_after_restart = cli(
        db_url,
        "show-location",
        "--world-id",
        world_id,
        "--character-id",
        second,
        "--location",
        "old_station",
    )
    assert view_after_restart.returncode == 0, view_after_restart.stderr
    assert _value(view_after_restart.stdout, "characters_total") == "2"
    assert CLAIM_FRAGMENT not in view_after_restart.stdout
    assert TRUTH_FRAGMENT not in view_after_restart.stdout

    shown_first = cli(
        db_url, "show-character", "--world-id", world_id, "--character-id", first
    )
    assert _value(shown_first.stdout, "knowledge_total") == "1"
    assert "KNOWLEDGE OBSERVATION LIKELY" in shown_first.stdout

    shown_second = cli(
        db_url, "show-character", "--world-id", world_id, "--character-id", second
    )
    assert _value(shown_second.stdout, "knowledge_total") == "0"

    events = cli(db_url, "events", world_id)
    assert _value(events.stdout, "events_total") == "8"
    assert events.stdout.count("INFORMATION_DISCOVERED") == 1
