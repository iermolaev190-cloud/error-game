"""Scenario: SHARE переживает перезапуск процесса.

CREATE WORLD → CREATE A и B → оба MOVE до old_station → A INSPECT
→ A SHARE B → RESTART процессов → у A наблюдение, у B переданное знание
с провенансом на A; журнал событий содержит KNOWLEDGE_SHARED.
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


def test_knowledge_sharing_survives_process_restart(
    tmp_path: Path,
    cli: CliRunner,
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'sharing.db').as_posix()}"

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

    sharer = characters["player-a"]
    receiver = characters["player-b"]

    for character_id in (sharer, receiver):
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

    inspect = cli(
        db_url,
        "inspect",
        "--world-id",
        world_id,
        "--character-id",
        sharer,
        "--target",
        "damaged_radio",
    )
    assert inspect.returncode == 0, inspect.stderr
    assert _value(inspect.stdout, "state_version") == "7"

    shared = cli(
        db_url,
        "share",
        "--world-id",
        world_id,
        "--character-id",
        sharer,
        "--to-character-id",
        receiver,
        "--information",
        "damaged_radio",
    )
    assert shared.returncode == 0, shared.stderr
    assert _value(shared.stdout, "already_known") == "False"
    assert _value(shared.stdout, "claim_type") == "CLAIM"
    assert _value(shared.stdout, "source") == "CHARACTER"
    assert _value(shared.stdout, "source_ref") == sharer
    assert _value(shared.stdout, "confidence") == "LIKELY"
    assert _value(shared.stdout, "state_version") == "8"

    # --- RESTART: новые процессы читают изменённый мир ---
    shown_sharer = cli(
        db_url, "show-character", "--world-id", world_id, "--character-id", sharer
    )
    assert shown_sharer.returncode == 0, shown_sharer.stderr
    assert _value(shown_sharer.stdout, "knowledge_total") == "1"
    assert "KNOWLEDGE FACT LIKELY" in shown_sharer.stdout
    assert f"KNOWLEDGE_PROVENANCE FACT OBSERVATION {sharer}" in shown_sharer.stdout
    assert CLAIM_FRAGMENT in shown_sharer.stdout

    shown_receiver = cli(
        db_url, "show-character", "--world-id", world_id, "--character-id", receiver
    )
    assert shown_receiver.returncode == 0, shown_receiver.stderr
    assert _value(shown_receiver.stdout, "knowledge_total") == "1"
    assert "KNOWLEDGE CLAIM LIKELY" in shown_receiver.stdout
    assert f"KNOWLEDGE_PROVENANCE CLAIM CHARACTER {sharer}" in shown_receiver.stdout
    assert CLAIM_FRAGMENT in shown_receiver.stdout
    assert TRUTH_FRAGMENT not in shown_receiver.stdout

    events = cli(db_url, "events", world_id)
    assert events.returncode == 0, events.stderr
    assert _value(events.stdout, "events_total") == "9"
    assert events.stdout.count("KNOWLEDGE_SHARED") == 1

    # Повторный SHARE после перезапуска — no-op без нового события.
    repeated = cli(
        db_url,
        "share",
        "--world-id",
        world_id,
        "--character-id",
        sharer,
        "--to-character-id",
        receiver,
        "--information",
        "damaged_radio",
    )
    assert repeated.returncode == 0, repeated.stderr
    assert _value(repeated.stdout, "already_known") == "True"
    assert _value(cli(db_url, "events", world_id).stdout, "events_total") == "9"
