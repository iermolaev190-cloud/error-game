"""Record the aggregate extra-tick event for one action."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import EventId, new_event_id
from world_error.domain.time.action_cost import CostTicks
from world_error.domain.world.instance import WorldInstance


def consume_action_cost(
    instance: WorldInstance,
    *,
    action: str,
    action_event: Event,
    cost: CostTicks | int | None,
    now: datetime,
    new_event_id_factory: Callable[[], EventId] = new_event_id,
) -> Event | None:
    if cost is None:
        return None
    ticks = int(cost if isinstance(cost, CostTicks) else CostTicks(cost))
    from_tick = instance.state.world_tick - 1
    cost_event = Event(
        id=new_event_id_factory(),
        world_instance_id=instance.id,
        type=EventType.ACTION_COST_TICK_CONSUMED,
        created_at=now,
        executed_at=now,
        actor=action_event.actor,
        target=action_event.target,
        cause=f"event:{action_event.id}",
        payload={
            "action": action,
            "cost": ticks,
            "from_tick": from_tick,
            "to_tick": from_tick + ticks,
        },
        result="success",
    )
    instance.register_action_cost(cost_event, from_tick=from_tick, cost_ticks=ticks)
    return cost_event
