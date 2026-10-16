"""Scenario: NPC живут в мире без игрока и переживают перезапуск процесса.

CREATE WORLD → персонаж-наблюдатель → show-location (NPC видны)
→ NPC исчезает (MISSING) и пропадает из проекции → NPC двигается и сам находит улику
→ RESTART → статусы, локации, знание NPC и журнал событий сохранены.

Знание NPC не выводится игровым CLI (debug-инструменты — Phase 26), поэтому его
сохранность проверяется отдельным читающим процессом через библиотеку.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

CHAT_ID = "-1001"
CLAIM_FRAGMENT = "корпус вскрыт"
TRUTH_FRAGMENT = "намеренно"

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

CliRunner = Callable[..., subprocess.CompletedProcess[str]]

KNOWLEDGE_SCRIPT = """
import sys

from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import WorldInstanceId

world_id = WorldInstanceId(sys.argv[1])
npc_id = sys.argv[2]
container = Container.build(Settings())
try:
    with container.uow_factory() as uow:
        uow.world_instances.get(world_id)
        rows = uow.knowledge.list_for_subject(world_id, SubjectType.NPC, npc_id)
        print(f"npc_knowledge_total={len(rows)}")
        for row in rows:
            print(
                f"NPC_KNOWLEDGE {row.subject_id} {row.claim_type.value} "
                f"{row.source.value} {row.claim}"
            )
finally:
    container.dispose()
"""


def _value(output: str, key: str) -> str:
    match = re.search(rf"^{re.escape(key)}=(.+)$", output, re.MULTILINE)
    assert match is not None, f"в выводе нет {key}:\n{output}"
    return match.group(1).strip()


def _npc_id(output: str, name: str) -> str:
    match = re.search(rf"^NPC (npc_[0-9a-f]+) {re.escape(name)} ", output, re.MULTILINE)
    assert match is not None, f"в выводе нет NPC {name}:\n{output}"
    return match.group(1)


def _read_reader_process(db_url: str, script: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "WORLD_ERROR_DB_URL": db_url,
        "PYTHONPATH": str(SRC_DIR),
        "PYTHONIOENCODING": "utf-8",
    }
    return subprocess.run(
        [sys.executable, "-c", script, *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_npc_life_survives_process_restart(
    tmp_path: Path,
    cli: CliRunner,
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'npc_loop.db').as_posix()}"

    upgrade = alembic_upgrade(db_url)
    assert upgrade.returncode == 0, upgrade.stderr

    created_world = cli(
        db_url, "create-world", "--chat-id", CHAT_ID, "--seed", "42", "--environment", "TEST"
    )
    assert created_world.returncode == 0, created_world.stderr
    world_id = _value(created_world.stdout, "instance_id")

    observer = cli(
        db_url,
        "create-character",
        "--world-id",
        world_id,
        "--player-id",
        "player-a",
        "--name",
        "Аня",
    )
    assert observer.returncode == 0, observer.stderr
    observer_id = _value(observer.stdout, "character_id")

    # 1. NPC видны в публичной проекции локации (только имя и статус).
    base_view = cli(
        db_url,
        "show-location",
        "--world-id",
        world_id,
        "--character-id",
        observer_id,
        "--location",
        "base",
    )
    assert base_view.returncode == 0, base_view.stderr
    assert _value(base_view.stdout, "npcs_total") == "1"
    assert "Смотритель" in base_view.stdout
    assert "ACTIVE" in base_view.stdout
    assert "KEEP_BASE_RUNNING" not in base_view.stdout
    caretaker_id = _npc_id(base_view.stdout, "Смотритель")

    # 2. NPC исчезает: статус меняется событием, NPC пропадает из проекции.
    gone = cli(
        db_url, "npc-status", "--world-id", world_id, "--npc-id", caretaker_id, "--to", "MISSING"
    )
    assert gone.returncode == 0, gone.stderr
    assert _value(gone.stdout, "to") == "MISSING"

    shown_caretaker = cli(db_url, "show-npc", "--world-id", world_id, "--npc-id", caretaker_id)
    assert shown_caretaker.returncode == 0, shown_caretaker.stderr
    assert _value(shown_caretaker.stdout, "name") == "Смотритель"
    assert _value(shown_caretaker.stdout, "status") == "MISSING"
    assert "goals" not in shown_caretaker.stdout

    empty_view = cli(
        db_url,
        "show-location",
        "--world-id",
        world_id,
        "--character-id",
        observer_id,
        "--location",
        "base",
    )
    assert _value(empty_view.stdout, "npcs_total") == "0"
    assert empty_view.stdout.count("NPC ") == 0

    # 3. Наблюдатель идёт к старой станции (в лесу знакомится с разведчиком).
    forest_move = cli(
        db_url, "move", "--world-id", world_id, "--character-id", observer_id, "--to", "forest"
    )
    assert forest_move.returncode == 0, forest_move.stderr

    forest_view = cli(
        db_url,
        "show-location",
        "--world-id",
        world_id,
        "--character-id",
        observer_id,
        "--location",
        "forest",
    )
    assert forest_view.returncode == 0, forest_view.stderr
    assert "Разведчик" in forest_view.stdout
    scout_id = _npc_id(forest_view.stdout, "Разведчик")

    station_move = cli(
        db_url, "move", "--world-id", world_id, "--character-id", observer_id, "--to", "old_station"
    )
    assert station_move.returncode == 0, station_move.stderr

    station_view = cli(
        db_url,
        "show-location",
        "--world-id",
        world_id,
        "--character-id",
        observer_id,
        "--location",
        "old_station",
    )
    assert station_view.returncode == 0, station_view.stderr
    assert _value(station_view.stdout, "npcs_total") == "1"
    mechanic_id = _npc_id(station_view.stdout, "Механик")

    # 4. NPC двигается сам и сам находит улику — без участия игрока.
    scout_moved = cli(
        db_url, "npc-move", "--world-id", world_id, "--npc-id", scout_id, "--to", "old_station"
    )
    assert scout_moved.returncode == 0, scout_moved.stderr
    assert _value(scout_moved.stdout, "to") == "old_station"

    observed = cli(
        db_url,
        "npc-observe",
        "--world-id",
        world_id,
        "--npc-id",
        mechanic_id,
        "--information",
        "damaged_radio",
    )
    assert observed.returncode == 0, observed.stderr
    assert _value(observed.stdout, "already_known") == "False"
    assert _value(observed.stdout, "discovery_state") == "DISCOVERED"
    assert _value(observed.stdout, "discovered_by") == mechanic_id
    assert _value(observed.stdout, "state_version") == "6"

    # --- RESTART: новые процессы ---
    scout_after = cli(
        db_url,
        "show-npc",
        "--world-id",
        world_id,
        "--npc-id",
        scout_id,
    )
    assert scout_after.returncode == 0, scout_after.stderr
    assert _value(scout_after.stdout, "status") == "ACTIVE"
    assert _value(scout_after.stdout, "location_key") == "old_station"

    station_after = cli(
        db_url,
        "show-location",
        "--world-id",
        world_id,
        "--character-id",
        observer_id,
        "--location",
        "old_station",
    )
    assert _value(station_after.stdout, "npcs_total") == "2"
    assert "Смотритель" not in station_after.stdout
    assert CLAIM_FRAGMENT not in station_after.stdout
    assert TRUTH_FRAGMENT not in station_after.stdout

    events = cli(db_url, "events", world_id)
    assert events.returncode == 0, events.stderr
    assert _value(events.stdout, "events_total") == "7"
    assert events.stdout.count("NPC_STATUS_CHANGED") == 1
    assert events.stdout.count("NPC_MOVED") == 1
    assert events.stdout.count("INFORMATION_DISCOVERED") == 1
    assert events.stdout.count("CHARACTER_MOVED") == 2

    # Знание NPC сохранено — читающий процесс, не игровой CLI.
    reader = _read_reader_process(db_url, KNOWLEDGE_SCRIPT, world_id, mechanic_id)
    assert reader.returncode == 0, reader.stderr
    assert _value(reader.stdout, "npc_knowledge_total") == "1"
    assert "NPC_KNOWLEDGE" in reader.stdout
    assert CLAIM_FRAGMENT in reader.stdout
    assert TRUTH_FRAGMENT not in reader.stdout
