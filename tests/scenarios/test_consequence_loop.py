"""Scenario: PENDING-последствия выживают перезапуск и срабатывают на тике.

CREATE WORLD → персонаж → планирование отложенного последствия через CLI →
RESTART (новые процессы) → advance-tick до срока → последствие применено.

Знание и статус последствия читаются отдельным процессом: игровой CLI читающих
команд последствий не имеет (как и у отношений).
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

CONSEQUENCE_TOKENS = (
    "CONSEQUENCE",
    "consequence",
    "INFORMATIONAL",
    "RELATIONAL",
    "PHYSICAL",
    "csq_",
    "HIDDEN",
    "PERSONAL",
    "LOCAL",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

CliRunner = Callable[..., subprocess.CompletedProcess[str]]

READER_SCRIPT = """
import sys

from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import CharacterId, ConsequenceId, NpcId, WorldInstanceId

world_id = WorldInstanceId(sys.argv[1])
consequence_id = ConsequenceId(sys.argv[2])
npc_id = NpcId(sys.argv[3])
character_id = CharacterId(sys.argv[4])
container = Container.build(Settings())
try:
    engine = container.world_engine
    consequence = engine.get_consequence(world_id, consequence_id)
    print(f"status={consequence.status.value}")
    print(f"effect={consequence.effect.value}")
    print(f"payload={dict(consequence.payload)}")
    print(f"applied_event_id={'yes' if consequence.applied_event_id else 'no'}")
    npc_knowledge = list(engine.get_npc_knowledge(world_id, npc_id))
    print(f"npc_knowledge={len(npc_knowledge)}")
    print(f"npc_claims={tuple(item.claim for item in npc_knowledge)!r}")
    print(f"character_knowledge={len(list(engine.get_knowledge(world_id, character_id)))}")
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


def _event_id(output: str, event_type: str) -> str:
    match = re.search(rf"^EVENT (ev_[0-9a-f]+) {event_type} ", output, re.MULTILINE)
    assert match is not None, f"в выводе нет события {event_type}:\n{output}"
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


def test_pending_consequence_survives_restart_and_fires_on_tick(
    tmp_path: Path,
    cli: CliRunner,
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'consequence_loop.db').as_posix()}"

    upgrade = alembic_upgrade(db_url)
    assert upgrade.returncode == 0, upgrade.stderr

    created_world = cli(
        db_url, "create-world", "--chat-id", CHAT_ID, "--seed", "42", "--environment", "TEST"
    )
    assert created_world.returncode == 0, created_world.stderr
    world_id = _value(created_world.stdout, "instance_id")

    created_character = cli(
        db_url,
        "create-character",
        "--world-id",
        world_id,
        "--player-id",
        "player-a",
        "--name",
        "Аня",
    )
    assert created_character.returncode == 0, created_character.stderr
    character_id = _value(created_character.stdout, "character_id")

    base_view = cli(
        db_url,
        "show-location",
        "--world-id",
        world_id,
        "--character-id",
        character_id,
        "--location",
        "base",
    )
    assert base_view.returncode == 0, base_view.stderr
    caretaker_id = _npc_id(base_view.stdout, "Смотритель")

    events = cli(db_url, "events", world_id)
    assert events.returncode == 0, events.stderr
    cause_event_id = _event_id(events.stdout, "CHARACTER_CREATED")

    # Планируем отложенное последствие: через 2 тика Смотритель узнаёт об улике.
    scheduled = cli(
        db_url,
        "schedule-consequence",
        "--world-id",
        world_id,
        "--cause-event-id",
        cause_event_id,
        "--type",
        "INFORMATIONAL",
        "--scale",
        "LOCAL",
        "--visibility",
        "HIDDEN",
        "--trigger",
        "AFTER_TICKS",
        "--delay-ticks",
        "2",
        "--effect",
        "INFORMATIONAL_LEARN",
        "--payload",
        f'{{"npc_id": "{caretaker_id}", "information_key": "damaged_radio"}}',
    )
    assert scheduled.returncode == 0, scheduled.stderr
    consequence_id = _value(scheduled.stdout, "consequence_id")
    due_tick = int(_value(scheduled.stdout, "due_tick"))
    assert _value(scheduled.stdout, "status") == "PENDING"
    assert consequence_id.startswith("csq_")

    # --- RESTART: новые процессы ---
    before = _read_reader_process(
        db_url, READER_SCRIPT, world_id, consequence_id, caretaker_id, character_id
    )
    assert before.returncode == 0, before.stderr
    assert _value(before.stdout, "status") == "PENDING"
    assert _value(before.stdout, "npc_knowledge") == "0"

    ticks = cli(db_url, "show-world", world_id)
    assert ticks.returncode == 0, ticks.stderr
    current_tick = int(_value(ticks.stdout, "world_tick"))

    advanced = 0
    while current_tick < due_tick:
        result = cli(db_url, "advance-tick", world_id, "--cause", f"tick-{advanced}")
        assert result.returncode == 0, result.stderr
        advanced += 1
        current_tick = int(_value(result.stdout, "world_tick"))
        assert advanced <= 5, "слишком много тиков для срабатывания последствия"

    after = _read_reader_process(
        db_url, READER_SCRIPT, world_id, consequence_id, caretaker_id, character_id
    )
    assert after.returncode == 0, after.stderr
    assert _value(after.stdout, "status") == "APPLIED"
    assert _value(after.stdout, "effect") == "INFORMATIONAL_LEARN"
    assert _value(after.stdout, "applied_event_id") == "yes"
    assert _value(after.stdout, "npc_knowledge") == "1"
    assert _value(after.stdout, "character_knowledge") == "0"  # M4
    assert "'information_key': 'damaged_radio'" in after.stdout
    npc_claims = _value(after.stdout, "npc_claims")
    assert CLAIM_FRAGMENT in npc_claims
    assert TRUTH_FRAGMENT not in npc_claims

    # Последствия не раскрываются ни одной публичной командой.
    for command in (
        (
            "show-location",
            "--world-id",
            world_id,
            "--character-id",
            character_id,
            "--location",
            "base",
        ),
        ("show-npc", "--world-id", world_id, "--npc-id", caretaker_id),
        ("show-character", "--world-id", world_id, "--character-id", character_id),
    ):
        result = cli(db_url, *command)
        assert result.returncode == 0, result.stderr
        for token in CONSEQUENCE_TOKENS:
            assert token not in result.stdout, f"утечка {token}:\n{result.stdout}"

    all_events = cli(db_url, "events", world_id)
    assert _value(all_events.stdout, "events_total") == str(4 + advanced)
    assert all_events.stdout.count("CONSEQUENCE_CREATED") == 1
    assert all_events.stdout.count("NPC_LEARNED") == 1
