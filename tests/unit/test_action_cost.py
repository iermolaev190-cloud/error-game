from __future__ import annotations

from datetime import datetime, timezone

import pytest

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import DomainError, ErrorCode, EventId, WorldInstanceId
from world_error.domain.time.action_cost import CostTicks
from world_error.domain.world.instance import InstanceEnvironment, WorldInstance

NOW = datetime(2026, 10, 4, tzinfo=timezone.utc)


def test_cost_ticks_requires_a_positive_integer() -> None:
    assert int(CostTicks(3)) == 3
    for invalid in (0, -1, True, 1.5):
        with pytest.raises(DomainError) as exc_info:
            CostTicks(invalid)  # type: ignore[arg-type]
        assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_one_cost_event_advances_world_tick_by_cost_and_version_once() -> None:
    instance = WorldInstance.create(
        id=WorldInstanceId("wi_cost"),
        telegram_chat_id=-1001,
        seed=1,
        content_version="v1",
        environment=InstanceEnvironment.TEST,
        now=NOW,
    )
    first = Event(
        id=EventId("ev_move"),
        world_instance_id=instance.id,
        type=EventType.CHARACTER_MOVED,
        created_at=NOW,
        payload={"from": "base", "to": "forest"},
    )
    instance.register_applied_event(first)
    cost = CostTicks(3)
    cost_event = Event(
        id=EventId("ev_cost"),
        world_instance_id=instance.id,
        type=EventType.ACTION_COST_TICK_CONSUMED,
        created_at=NOW,
        cause="event:ev_move",
        payload={"action": "MOVE", "cost": int(cost), "from_tick": 0, "to_tick": 3},
    )

    instance.register_action_cost(cost_event, from_tick=0, cost_ticks=int(cost))

    assert instance.state.world_tick == 3
    assert instance.state.state_version == 2