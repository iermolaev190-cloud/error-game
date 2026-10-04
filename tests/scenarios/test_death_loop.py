"""Death and replacement-character state survive subprocess restarts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from world_error.domain.shared.kernel import CharacterId, WorldInstanceId

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

KILL_SCRIPT = """
import sys
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import CharacterId, WorldInstanceId

container = Container.build(Settings())
try:
    world_id = WorldInstanceId(sys.argv[1])
    character_id = CharacterId(sys.argv[2])
    cause_id = container.world_engine.get_events(world_id)[-1].id
    result = container.world_engine.kill_character(world_id, character_id, cause_event_id=cause_id)
    assert result.ok, result.error
    print(f'death_event_id={result.payload["death_event_id"]}')
finally:
    container.dispose()
"""

READ_SCRIPT = """
import sys
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import CharacterId, WorldInstanceId

container = Container.build(Settings())
try:
    world_id = WorldInstanceId(sys.argv[1])
    character_id = CharacterId(sys.argv[2])
    engine = container.world_engine
    character = engine.get_character(world_id, character_id)
    events = engine.get_events(world_id)
    print(f'lifecycle={character.lifecycle.value}')
    print(f'death_event_id={character.death_event_id or ""}')
    print(f'death_cause_event_id={character.death_cause_event_id or ""}')
    print(f'death_event_count={sum(event.type.value == "DEATH_EVENT" for event in events)}')
    print(f'cause_exists={int(any(event.id == character.death_cause_event_id for event in events))}')
finally:
    container.dispose()
"""

SPAWN_SCRIPT = """
import sys
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import CharacterId, WorldInstanceId

container = Container.build(Settings())
try:
    world_id = WorldInstanceId(sys.argv[1])
    result = container.world_engine.spawn_new_character(
        world_id, player_id='player-a', name='Новый'
    )
    assert result.ok, result.error
    character_id = result.payload['character_id']
    print(f'character_id={character_id}')
    print(f'knowledge_count={len(container.world_engine.get_knowledge(world_id, CharacterId(character_id)))}')
finally:
    container.dispose()
"""


def _run_python(db_url: str, script: str, *args: str) -> subprocess.CompletedProcess[str]:
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


def _value(output: str, key: str) -> str:
    for line in output.splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"output has no {key}:\n{output}")


def test_death_and_new_character_survive_process_restart(
    tmp_path: Path,
    cli: Callable[..., subprocess.CompletedProcess[str]],
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'death_loop.db').as_posix()}"
    upgrade = alembic_upgrade(db_url)
    assert upgrade.returncode == 0, upgrade.stderr
    created = cli(
        db_url, "create-world", "--chat-id", "-1001", "--seed", "42", "--environment", "TEST"
    )
    assert created.returncode == 0, created.stderr
    world_id = _value(created.stdout, "instance_id")
    character = cli(
        db_url,
        "create-character",
        "--world-id",
        world_id,
        "--player-id",
        "player-a",
        "--name",
        "Старый",
    )
    assert character.returncode == 0, character.stderr
    character_id = _value(character.stdout, "character_id")

    killed = _run_python(db_url, KILL_SCRIPT, world_id, character_id)
    assert killed.returncode == 0, killed.stderr
    death_event_id = _value(killed.stdout, "death_event_id")

    after_restart = _run_python(db_url, READ_SCRIPT, world_id, character_id)
    assert after_restart.returncode == 0, after_restart.stderr
    assert _value(after_restart.stdout, "lifecycle") == "DEAD"
    assert _value(after_restart.stdout, "death_event_id") == death_event_id
    assert _value(after_restart.stdout, "death_cause_event_id").startswith("ev_")
    assert _value(after_restart.stdout, "death_event_count") == "1"
    assert _value(after_restart.stdout, "cause_exists") == "1"

    spawned = _run_python(db_url, SPAWN_SCRIPT, world_id)
    assert spawned.returncode == 0, spawned.stderr
    assert _value(spawned.stdout, "knowledge_count") == "0"
