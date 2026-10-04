"""Scenario: отношения переживают перезапуск процесса и не раскрываются игроку.

CREATE WORLD → персонаж → значимое действие BETRAYED → обратное отношение
создаётся отдельной командой → RESTART → уровни сохранены и асимметричны,
show-location / show-npc / show-character отношений не содержат.

Читающих команд отношений в CLI нет намеренно: проверка состояния выполняется
отдельным читающим процессом через библиотеку.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

CHAT_ID = "-1001"

RELATIONSHIP_TOKENS = (
    "TRUST",
    "SUSPICION",
    "HOSTILE",
    "WARY",
    "NEUTRAL",
    "FRIENDLY",
    "DEVOTED",
    "NONE",
    "LOW",
    "MEDIUM",
    "HIGH",
    "RELATIONSHIP_CHANGED",
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

CliRunner = Callable[..., subprocess.CompletedProcess[str]]

READER_SCRIPT = """
import sys

from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import RelationshipKind, SubjectRef
from world_error.domain.shared.kernel import WorldInstanceId

world_id = WorldInstanceId(sys.argv[1])
holder = SubjectRef(SubjectType.NPC, sys.argv[2])
subject = SubjectRef(SubjectType.CHARACTER, sys.argv[3])
container = Container.build(Settings())
try:
    engine = container.world_engine
    trust = engine.get_relationship(
        world_id, holder=holder, subject=subject, kind=RelationshipKind.TRUST
    )
    suspicion = engine.get_relationship(
        world_id, holder=holder, subject=subject, kind=RelationshipKind.SUSPICION
    )
    reverse = engine.get_relationship(
        world_id, holder=subject, subject=holder, kind=RelationshipKind.TRUST
    )
    print(f"trust={trust.level.value if trust else 'NONE_RECORD'}")
    print(f"suspicion={suspicion.level.value if suspicion else 'NONE_RECORD'}")
    print(f"reverse_trust={reverse.level.value if reverse else 'NONE_RECORD'}")
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


def _assert_no_relationship_tokens(rendered: str) -> None:
    pattern = r"\b(" + "|".join(re.escape(token) for token in RELATIONSHIP_TOKENS) + r")\b"
    leaked = sorted(set(re.findall(pattern, rendered)))
    assert not leaked, f"утечка отношений: {leaked}\n{rendered}"
    assert "rel_" not in rendered, f"утечка id отношения:\n{rendered}"


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


def test_relationship_survives_process_restart_and_stays_private(
    tmp_path: Path,
    cli: CliRunner,
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'relationship_loop.db').as_posix()}"

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
    npc_id = _npc_id(base_view.stdout, "Смотритель")

    # 1. Значимое действие: держатель (NPC) меняет мнение о действующем (игроке).
    betrayed = cli(
        db_url,
        "significant-action",
        "--world-id",
        world_id,
        "--actor-type",
        "CHARACTER",
        "--actor-id",
        character_id,
        "--holder-type",
        "NPC",
        "--holder-id",
        npc_id,
        "--action",
        "BETRAYED",
    )
    assert betrayed.returncode == 0, betrayed.stderr
    assert _value(betrayed.stdout, "changed") == "True"
    assert _value(betrayed.stdout, "reason") == "BETRAYED"
    assert _value(betrayed.stdout, "state_version") == "2"

    # 2. Обратное отношение создаётся отдельно — асимметрия видна и в CLI.
    reverse = cli(
        db_url,
        "relationship-change",
        "--world-id",
        world_id,
        "--holder-type",
        "CHARACTER",
        "--holder-id",
        character_id,
        "--subject-type",
        "NPC",
        "--subject-id",
        npc_id,
        "--kind",
        "TRUST",
        "--direction",
        "INCREASE",
    )
    assert reverse.returncode == 0, reverse.stderr
    assert _value(reverse.stdout, "from") == "NEUTRAL"
    assert _value(reverse.stdout, "to") == "FRIENDLY"
    assert _value(reverse.stdout, "state_version") == "3"

    # 3. Отношения не раскрываются ни одной публичной командой.
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
        ("show-npc", "--world-id", world_id, "--npc-id", npc_id),
        ("show-character", "--world-id", world_id, "--character-id", character_id),
    ):
        result = cli(db_url, *command)
        assert result.returncode == 0, result.stderr
        _assert_no_relationship_tokens(result.stdout)

    events = cli(db_url, "events", world_id)
    assert events.returncode == 0, events.stderr
    assert _value(events.stdout, "events_total") == "4"
    assert events.stdout.count("RELATIONSHIP_CHANGED") == 2

    # --- RESTART: отдельный читающий процесс ---
    reader = _read_reader_process(db_url, READER_SCRIPT, world_id, npc_id, character_id)
    assert reader.returncode == 0, reader.stderr
    assert _value(reader.stdout, "trust") == "WARY"
    assert _value(reader.stdout, "suspicion") == "LOW"
    assert _value(reader.stdout, "reverse_trust") == "FRIENDLY"
