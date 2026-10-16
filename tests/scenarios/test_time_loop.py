"""Scenario: pending scheduled events survive process restart and fire on tick."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

from world_error.domain.shared.kernel import ScheduledEventId, WorldInstanceId

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

SCHEDULE_SCRIPT = """
import sys
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import ScheduledEventId, WorldInstanceId
from world_error.domain.time.scheduled_event import ScheduledTriggerKind

container = Container.build(Settings())
try:
    world_id = WorldInstanceId(sys.argv[1])
    cause = container.world_engine.get_events(world_id)[0].id
    result = container.world_engine.schedule_event(
        world_id,
        cause_event_id=cause,
        event_key="arrival",
        idempotency_key="arrival-after-restart",
        trigger_kind=ScheduledTriggerKind.AT_TICK,
        due_tick=3,
        payload={"location_key": "base"},
    )
    assert result.ok, result.error
    scheduled_id = ScheduledEventId(result.payload["scheduled_event_id"])
    caretaker_id = next(
        npc.id for npc in container.world_engine.get_npcs(world_id) if npc.key == "caretaker"
    )
    print(f"scheduled_event_id={result.payload['scheduled_event_id']}")
    print(f"status={container.world_engine.get_scheduled_event(world_id, scheduled_id).status.value}")
    print(f"caretaker_id={caretaker_id}")
finally:
    container.dispose()
"""

READ_SCRIPT = """
import sys
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import ScheduledEventId, WorldInstanceId

container = Container.build(Settings())
try:
    world_id = WorldInstanceId(sys.argv[1])
    scheduled_id = ScheduledEventId(sys.argv[2])
    item = container.world_engine.get_scheduled_event(world_id, scheduled_id)
    print(f"status={item.status.value}")
    print(f"triggered_event_id={item.triggered_event_id or ''}")
    print(f"scheduled_event_type_count={sum(
        event.type.value == 'SCHEDULED_EVENT_TRIGGERED'
        for event in container.world_engine.get_events(world_id)
    )}")
finally:
    container.dispose()
"""

PENDING_CONSEQUENCES_SCRIPT = """
import sys
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.consequences.consequence import ConsequenceTrigger
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect, ConsequenceScale, ConsequenceType, ConsequenceVisibility,
)
from world_error.domain.shared.kernel import WorldInstanceId

container = Container.build(Settings())
try:
    world_id = WorldInstanceId(sys.argv[1])
    npc_id = next(npc.id for npc in container.world_engine.get_npcs(world_id) if npc.key == 'caretaker')
    for label in ('cancel-me', 'transform-me'):
        cause = container.world_engine.get_events(world_id)[-1].id
        result = container.world_engine.schedule_consequence(
            world_id,
            cause_event_ids=(cause,),
            type=ConsequenceType.INFORMATIONAL,
            scale=ConsequenceScale.LOCAL,
            visibility=ConsequenceVisibility.HIDDEN,
            trigger=ConsequenceTrigger.after_ticks(100),
            effect=ConsequenceEffect.INFORMATIONAL_LEARN,
            payload={'npc_id': str(npc_id), 'information_key': 'damaged_radio'},
        )
        assert result.ok, result.error
        print(f'{label}={result.payload["consequence_id"]}')
finally:
    container.dispose()
"""

CANCEL_TRANSFORM_SCRIPT = """
import sys
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.consequences.consequence import ConsequenceTrigger
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect, ConsequenceScale, ConsequenceType, ConsequenceVisibility,
)
from world_error.domain.shared.kernel import ConsequenceId, WorldInstanceId

container = Container.build(Settings())
try:
    world_id = WorldInstanceId(sys.argv[1])
    cancel_id = ConsequenceId(sys.argv[2])
    transform_id = ConsequenceId(sys.argv[3])
    engine = container.world_engine
    assert engine.get_consequence(world_id, cancel_id).status.value == 'PENDING'
    assert engine.get_consequence(world_id, transform_id).status.value == 'PENDING'
    cancelled = engine.cancel_consequence(world_id, cancel_id)
    assert cancelled.ok, cancelled.error
    transformed = engine.transform_consequence(
        world_id,
        transform_id,
        type=ConsequenceType.INFORMATIONAL,
        scale=ConsequenceScale.REGIONAL,
        visibility=ConsequenceVisibility.HIDDEN,
        trigger=ConsequenceTrigger.after_ticks(200),
        effect=ConsequenceEffect.INFORMATIONAL_LEARN,
        payload=dict(engine.get_consequence(world_id, transform_id).payload),
    )
    assert transformed.ok, transformed.error
    print(f'replacement_id={transformed.payload["transformed_to"]}')
finally:
    container.dispose()
"""

READ_CONSEQUENCES_SCRIPT = """
import sys
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import ConsequenceId, WorldInstanceId

container = Container.build(Settings())
try:
    engine = container.world_engine
    world_id = WorldInstanceId(sys.argv[1])
    for label, raw_id in zip(('cancel', 'transform', 'replacement'), sys.argv[2:]):
        item = engine.get_consequence(world_id, ConsequenceId(raw_id))
        print(f'{label}_status={item.status.value}')
    events = engine.get_events(world_id)
    print(f'cancel_event_count={sum(event.type.value == "CONSEQUENCE_CANCELLED" for event in events)}')
    print(f'transform_event_count={sum(event.type.value == "CONSEQUENCE_TRANSFORMED" for event in events)}')
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
    match = re.search(rf"^{re.escape(key)}=(.*)$", output, re.MULTILINE)
    assert match is not None, f"в выводе нет {key}:\n{output}"
    return match.group(1).strip()


def test_pending_scheduled_event_survives_restart_and_fires_on_tick(
    tmp_path: Path,
    cli: Callable[..., subprocess.CompletedProcess[str]],
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'time_loop.db').as_posix()}"
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
        "Аня",
    )
    assert character.returncode == 0, character.stderr
    character_id = _value(character.stdout, "character_id")

    scheduled = _run_python(db_url, SCHEDULE_SCRIPT, world_id)
    assert scheduled.returncode == 0, scheduled.stderr
    scheduled_id = _value(scheduled.stdout, "scheduled_event_id")
    caretaker_id = _value(scheduled.stdout, "caretaker_id")
    assert _value(scheduled.stdout, "status") == "PENDING"

    public_outputs = (
        cli(
            db_url,
            "show-location",
            "--world-id",
            world_id,
            "--character-id",
            character_id,
            "--location",
            "base",
        ),
        cli(db_url, "show-npc", "--world-id", world_id, "--npc-id", caretaker_id),
        cli(db_url, "show-character", "--world-id", world_id, "--character-id", character_id),
    )
    for output in public_outputs:
        assert output.returncode == 0, output.stderr
        for private_token in (scheduled_id, "arrival-after-restart", "arrival"):
            assert private_token not in output.stdout

    after_restart_before_due = _run_python(db_url, READ_SCRIPT, world_id, scheduled_id)
    assert after_restart_before_due.returncode == 0, after_restart_before_due.stderr
    assert _value(after_restart_before_due.stdout, "status") == "PENDING"

    advanced = cli(db_url, "advance-tick", world_id, "--cause", "time-loop")
    assert advanced.returncode == 0, advanced.stderr

    after_restart_after_due = _run_python(db_url, READ_SCRIPT, world_id, scheduled_id)
    assert after_restart_after_due.returncode == 0, after_restart_after_due.stderr
    assert _value(after_restart_after_due.stdout, "status") == "APPLIED"
    assert _value(after_restart_after_due.stdout, "triggered_event_id").startswith("ev_")
    assert _value(after_restart_after_due.stdout, "scheduled_event_type_count") == "1"


def test_pending_consequences_survive_restart_before_cancel_and_transform(
    tmp_path: Path,
    cli: Callable[..., subprocess.CompletedProcess[str]],
    alembic_upgrade: Callable[[str], subprocess.CompletedProcess[str]],
) -> None:
    db_url = f"sqlite+pysqlite:///{(tmp_path / 'cancel_transform.db').as_posix()}"
    upgrade = alembic_upgrade(db_url)
    assert upgrade.returncode == 0, upgrade.stderr
    created = cli(
        db_url, "create-world", "--chat-id", "-1002", "--seed", "42", "--environment", "TEST"
    )
    assert created.returncode == 0, created.stderr
    world_id = _value(created.stdout, "instance_id")

    pending = _run_python(db_url, PENDING_CONSEQUENCES_SCRIPT, world_id)
    assert pending.returncode == 0, pending.stderr
    cancel_id = _value(pending.stdout, "cancel-me")
    transform_id = _value(pending.stdout, "transform-me")

    changed = _run_python(db_url, CANCEL_TRANSFORM_SCRIPT, world_id, cancel_id, transform_id)
    assert changed.returncode == 0, changed.stderr
    replacement_id = _value(changed.stdout, "replacement_id")

    after_restart = _run_python(
        db_url, READ_CONSEQUENCES_SCRIPT, world_id, cancel_id, transform_id, replacement_id
    )
    assert after_restart.returncode == 0, after_restart.stderr
    assert _value(after_restart.stdout, "cancel_status") == "CANCELLED"
    assert _value(after_restart.stdout, "transform_status") == "TRANSFORMED"
    assert _value(after_restart.stdout, "replacement_status") == "PENDING"
    assert _value(after_restart.stdout, "cancel_event_count") == "1"
    assert _value(after_restart.stdout, "transform_event_count") == "1"