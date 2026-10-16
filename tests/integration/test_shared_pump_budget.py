"""The scheduled-event and consequence pumps share one cascade budget."""

from __future__ import annotations

from world_error.application.commands.schedule_consequence import (
    ScheduleConsequenceCommand,
    ScheduleConsequenceHandler,
)
from world_error.application.commands.schedule_event import ScheduleEventCommand, ScheduleEventHandler
from world_error.application.services.world_engine import WorldEngine
from world_error.domain.consequences.consequence import ConsequenceTrigger
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceStatus,
    ConsequenceType,
    ConsequenceVisibility,
)
from world_error.domain.events.event import EventType
from world_error.domain.shared.kernel import SystemClock
from world_error.domain.time.scheduled_event import ScheduledTriggerKind
from world_error.domain.world.instance import WorldInstance


def test_both_pumps_stop_at_one_shared_limit(
    world_engine: WorldEngine, uow_factory, catalog
) -> None:  # noqa: ANN001
    instance: WorldInstance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    caretaker = next(npc for npc in world_engine.get_npcs(instance.id) if npc.key == "caretaker")
    clock = SystemClock()
    schedule_handler = ScheduleEventHandler(uow_factory, clock)
    consequence_handler = ScheduleConsequenceHandler(uow_factory, clock)

    cause_event_id = world_engine.get_events(instance.id)[-1].id
    for index in range(8):
        scheduled = schedule_handler.handle(
            ScheduleEventCommand(
                world_instance_id=instance.id,
                cause_event_id=cause_event_id,
                event_key=f"cascade-{index}",
                idempotency_key=f"cascade-{index}",
                trigger_kind=ScheduledTriggerKind.AT_TICK,
                due_tick=0,
                payload={},
            )
        )
        assert scheduled.ok is True, scheduled.error
        cause_event_id = scheduled.event_ids[-1]

    for index in range(12):
        consequence = consequence_handler.handle(
            ScheduleConsequenceCommand(
                world_instance_id=instance.id,
                cause_event_ids=(cause_event_id,),
                type=ConsequenceType.INFORMATIONAL,
                scale=ConsequenceScale.LOCAL,
                visibility=ConsequenceVisibility.HIDDEN,
                trigger=ConsequenceTrigger.immediate(),
                effect=ConsequenceEffect.INFORMATIONAL_LEARN,
                payload={"npc_id": str(caretaker.id), "information_key": "damaged_radio"},
                rule_key=f"budget-{index}",
            )
        )
        assert consequence.ok is True, consequence.error
        cause_event_id = consequence.event_ids[-1]

    outcome = world_engine.pump_time(instance.id)

    assert outcome.steps == 16
    assert outcome.limit_reached is True
    assert len(outcome.scheduled.applied) == 8
    assert len(outcome.consequences.applied) == 8
    pending = [
        item
        for item in world_engine.list_consequences(instance.id)
        if item.status is ConsequenceStatus.PENDING
    ]
    assert len(pending) == 4
    assert len(
        [event for event in world_engine.get_events(instance.id) if event.type is EventType.SCHEDULED_EVENT_TRIGGERED]
    ) == 8
