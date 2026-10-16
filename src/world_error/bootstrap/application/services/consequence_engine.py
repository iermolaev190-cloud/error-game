"""Насос последствий: детерминированная обработка без демонов и таймеров.

Три вещи, которые делает насос:

1. **Материализация правил.** Для каждого события мира, на которое есть правило
   контента, создаётся ПENDING-последствие. Идемпотентность гарантирована
   уникальностью ``(instance, rule_key, source_event_id)``, поэтому повторный
   прогон (в том числе после перезапуска процесса) ничего не дублирует.
2. **Применение созревших.** Созревшее последствие — это своя транзакция:
   строка переходит в APPLIED, и в той же транзакции пишется событие-эффект с
   ``cause="consequence:<id>"``.
3. **Каскад.** Применённый эффект может стать причиной следующего последствия;
   цикл ограничен ``MAX_CASCADE_STEPS``. Уже применённые последствия при
   достижении лимита **не откатываются**: лимит лишь останавливает насос.

Насос вызывается после каждой команды, добавившей события, и при ``advance-tick``.
Если незакрытых последствий нет, он не делает ничего — прямые действия мира
работают ровно как раньше.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from world_error.application.commands._subjects import resolve_subject
from world_error.application.commands.schedule_consequence import (
    ScheduleConsequenceCommand,
    ScheduleConsequenceHandler,
)
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.consequences.consequence import (
    Consequence,
    consequence_cause_of,
)
from world_error.domain.consequences.rules import ConsequenceRule
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    TriggerKind,
)
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.npcs.npc import NpcStatus
from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipDirection,
    RelationshipKind,
    SubjectRef,
    baseline_level,
    step_level,
)
from world_error.domain.shared.kernel import (
    Clock,
    ConsequenceId,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    NpcId,
    WorldInstanceId,
    new_consequence_id,
    new_event_id,
    new_knowledge_id,
    new_relationship_id,
)

# Лимит каскада: защита от циклов (§58–60). При достижении насос останавливается,
# но уже применённые последствия остаются применёнными.
MAX_CASCADE_STEPS = 16


@dataclass(frozen=True, slots=True)
class PumpOutcome:
    """Что сделал насос: применённые, проваленные и порождённые события."""

    applied: tuple[ConsequenceId, ...] = ()
    failed: tuple[ConsequenceId, ...] = ()
    event_ids: tuple[EventId, ...] = ()
    failed_rules: tuple[str, ...] = ()
    limit_reached: bool = False
    steps: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.applied or self.failed or self.failed_rules)


class ConsequenceEngine:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        catalog: ContentCatalog,
        schedule_handler: ScheduleConsequenceHandler,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_consequence_id_factory: Callable[[], ConsequenceId] = new_consequence_id,
        max_cascade_steps: int = MAX_CASCADE_STEPS,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog
        self._schedule = schedule_handler
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_consequence_id = new_consequence_id_factory
        self._max_cascade_steps = max_cascade_steps

    @property
    def max_cascade_steps(self) -> int:
        return self._max_cascade_steps

    # --- основной цикл ------------------------------------------------------

    def pump(
        self, world_instance_id: WorldInstanceId, *, max_steps: int | None = None
    ) -> PumpOutcome:
        applied: list[ConsequenceId] = []
        failed: list[ConsequenceId] = []
        event_ids: list[EventId] = []
        failed_rules: list[str] = []
        steps = 0
        limit_reached = False
        step_limit = self._max_cascade_steps if max_steps is None else min(
            self._max_cascade_steps, max(0, max_steps)
        )

        while True:
            progressed = False

            created, rule_failures = self._materialize_rules(world_instance_id)
            if created:
                event_ids.extend(created)
                progressed = True
            failed_rules.extend(rule_failures)

            if steps >= step_limit:
                limit_reached = self._has_due(world_instance_id)
                break

            outcome = self._apply_next_due(world_instance_id)
            if outcome is not None:
                consequence_id, effect_event_id, applied_ok = outcome
                (applied if applied_ok else failed).append(consequence_id)
                if effect_event_id is not None:
                    event_ids.append(effect_event_id)
                progressed = True
                steps += 1

            if not progressed:
                break
            if steps >= step_limit:
                limit_reached = self._has_due(world_instance_id)
                break

        return PumpOutcome(
            applied=tuple(applied),
            failed=tuple(failed),
            event_ids=tuple(event_ids),
            failed_rules=tuple(failed_rules),
            limit_reached=limit_reached,
            steps=steps,
        )

    def has_due(self, world_instance_id: WorldInstanceId) -> bool:
        return self._has_due(world_instance_id)

    # --- правила ------------------------------------------------------------

    def _materialize_rules(
        self, world_instance_id: WorldInstanceId
    ) -> tuple[list[EventId], list[str]]:
        rules = tuple(self._catalog.rules.values())
        if not rules:
            return ([], [])

        candidates: list[tuple[ConsequenceRule, Event, dict[str, Any]]] = []
        failures: list[str] = []
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            events = uow.events.list_for_instance(instance.id)
            for rule in rules:
                for event in events:
                    if not rule.matches(event):
                        continue
                    if (
                        uow.consequences.find_by_rule(instance.id, rule.key, event.id)
                        is not None
                    ):
                        continue
                    try:
                        payload = self._resolve_effect_keys(uow, instance, rule)
                    except DomainError:
                        # Правило ссылается на отсутствующий в этом мире контент:
                        # тихо терять такое нельзя, поэтому сообщаем наверх.
                        failures.append(rule.key)
                        continue
                    candidates.append((rule, event, payload))

        created: list[EventId] = []
        for rule, event, payload in candidates:
            result = self._schedule.handle(
                ScheduleConsequenceCommand(
                    world_instance_id=world_instance_id,
                    cause_event_ids=(event.id,),
                    type=rule.type,
                    scale=rule.scale,
                    visibility=rule.visibility,
                    trigger=rule.trigger,
                    effect=rule.effect,
                    payload=payload,
                    rule_key=rule.key,
                    cause="consequence_rule",
                )
            )
            if result.ok:
                created.extend(result.event_ids)
            else:
                failures.append(rule.key)
        return (created, failures)

    def _resolve_effect_keys(
        self, uow, instance, rule: ConsequenceRule  # noqa: ANN001
    ) -> dict[str, Any]:
        """Ключи контента → идентификаторы конкретного INSTANCE."""
        keys = dict(rule.effect_keys)
        if rule.effect is ConsequenceEffect.INFORMATIONAL_LEARN:
            npc = uow.npcs.get_by_key(instance.id, str(keys["npc_key"]))
            return {
                "npc_id": str(npc.id),
                "information_key": str(keys["information_key"]),
            }
        if rule.effect in (
            ConsequenceEffect.PHYSICAL_STATUS_CHANGE,
            ConsequenceEffect.PHYSICAL_RELOCATE,
        ):
            npc = uow.npcs.get_by_key(instance.id, str(keys["npc_key"]))
            resolved: dict[str, Any] = {"npc_id": str(npc.id)}
            if rule.effect is ConsequenceEffect.PHYSICAL_STATUS_CHANGE:
                resolved["status"] = str(keys["status"])
            else:
                resolved["to_location_key"] = str(keys["to_location_key"])
            return resolved

        holder = uow.npcs.get_by_key(instance.id, str(keys["holder_key"]))
        subject = uow.npcs.get_by_key(instance.id, str(keys["subject_key"]))
        return {
            "holder_type": SubjectType.NPC.value,
            "holder_id": str(holder.id),
            "subject_type": SubjectType.NPC.value,
            "subject_id": str(subject.id),
            "kind": str(keys["kind"]),
            "direction": str(keys["direction"]),
        }

    # --- применение ---------------------------------------------------------

    def _is_due(self, uow, instance, consequence: Consequence) -> bool:  # noqa: ANN001
        trigger = consequence.trigger
        if trigger.kind is TriggerKind.ON_EVENT_TYPE:
            # Сравнение по порядку событий (seq), а не по времени: проверка
            # устойчива к перезапуску процесса.
            return uow.events.has_event_of_type_since(
                instance.id, trigger.event_type, consequence.source_event_id
            )
        return trigger.tick_is_due(
            current_tick=instance.state.world_tick, due_tick=consequence.due_tick
        )

    def _has_due(self, world_instance_id: WorldInstanceId) -> bool:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            return any(
                self._is_due(uow, instance, consequence)
                for consequence in uow.consequences.list_pending(instance.id)
            )

    def _apply_next_due(
        self, world_instance_id: WorldInstanceId
    ) -> tuple[ConsequenceId, EventId | None, bool] | None:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            due = next(
                (
                    consequence
                    for consequence in uow.consequences.list_pending(instance.id)
                    if self._is_due(uow, instance, consequence)
                ),
                None,
            )
            consequence_id = None if due is None else due.id
        if consequence_id is None:
            return None
        event_id, applied_ok = self._apply_consequence(world_instance_id, consequence_id)
        return (consequence_id, event_id, applied_ok)

    def _apply_consequence(
        self, world_instance_id: WorldInstanceId, consequence_id: ConsequenceId
    ) -> tuple[EventId | None, bool]:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            expected_version = instance.state.state_version
            now = self._clock.now()
            consequence = uow.consequences.get(instance.id, consequence_id)

            if not consequence.can_apply():
                # Идемпотентность: повторное применение уже закрытого
                # последствия не порождает второго события.
                return (consequence.applied_event_id, True)

            try:
                event = self._effect_event(uow, instance, consequence, now)
            except DomainError as exc:
                return self._fail_consequence(
                    uow, instance, consequence, expected_version, now, exc
                )

            if event is None:
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.CONSEQUENCE_APPLIED,
                    created_at=now,
                    executed_at=now,
                    actor=None,
                    target=str(consequence.id),
                    cause=consequence_cause_of(consequence.id),
                    payload={
                        "consequence_id": str(consequence.id),
                        "effect": consequence.effect.value,
                        "effect_payload": dict(consequence.payload),
                        "cause_event_ids": [
                            str(cause.event_id) for cause in consequence.causes
                        ],
                        "world_changed": False,
                    },
                    result="applied_without_world_change",
                )
                instance.register_applied_event(event)

            consequence.mark_applied(event_id=event.id, now=now)
            uow.consequences.save(consequence)
            uow.world_instances.save(instance, expected_state_version=expected_version)
            uow.events.append(event)
            uow.commit()
            return (event.id, True)

    def _fail_consequence(
        self,
        uow,  # noqa: ANN001
        instance,  # noqa: ANN001
        consequence: Consequence,
        expected_version: int,
        now: datetime,
        error: DomainError,
    ) -> tuple[EventId, bool]:
        """Эффект невозможен: FAILED + CONSEQUENCE_FAILED, каскад продолжается (§79)."""
        event = Event(
            id=self._new_event_id(),
            world_instance_id=instance.id,
            type=EventType.CONSEQUENCE_FAILED,
            created_at=now,
            executed_at=now,
            actor=None,
            target=str(consequence.id),
            cause=consequence_cause_of(consequence.id),
            payload={
                "consequence_id": str(consequence.id),
                "effect": consequence.effect.value,
                "reason": error.code.value,
                "message": error.message,
                "cause_event_ids": [str(cause.event_id) for cause in consequence.causes],
            },
            result="failed",
        )
        instance.register_applied_event(event)
        consequence.mark_failed(now=now)
        uow.consequences.save(consequence)
        uow.world_instances.save(instance, expected_state_version=expected_version)
        uow.events.append(event)
        uow.commit()
        return (event.id, False)

    # --- эффекты ------------------------------------------------------------

    def _effect_event(
        self,
        uow,  # noqa: ANN001
        instance,  # noqa: ANN001
        consequence: Consequence,
        now: datetime,
    ) -> Event | None:
        effect = consequence.effect
        if effect is ConsequenceEffect.INFORMATIONAL_LEARN:
            return self._informational_learn(uow, instance, consequence, now)
        if effect is ConsequenceEffect.RELATIONAL_SHIFT:
            return self._relational_shift(uow, instance, consequence, now)
        if effect is ConsequenceEffect.PHYSICAL_STATUS_CHANGE:
            return self._physical_status_change(uow, instance, consequence, now)
        if effect is ConsequenceEffect.PHYSICAL_RELOCATE:
            return self._physical_relocate(uow, instance, consequence, now)
        raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported effect: {effect}")

    def _informational_learn(
        self, uow, instance, consequence: Consequence, now: datetime  # noqa: ANN001
    ) -> Event | None:
        """Знание получает **NPC**. Пути «последствие → знание игрока» не существует."""
        payload: Mapping[str, Any] = consequence.payload
        npc = uow.npcs.get(instance.id, NpcId(str(payload["npc_id"])))
        information = uow.information.get_by_key(instance.id, str(payload["information_key"]))
        if (
            uow.knowledge.find(instance.id, SubjectType.NPC, str(npc.id), information.id)
            is not None
        ):
            return None

        definition = self._catalog.information_definition(information.key)
        claim = str(payload.get("claim") or definition.content)
        claim_type = ClaimType(str(payload.get("claim_type") or ClaimType.FACT.value))
        source = KnowledgeSource(str(payload.get("source") or KnowledgeSource.OBSERVATION.value))
        confidence = KnowledgeConfidence(
            str(payload.get("confidence") or KnowledgeConfidence.LIKELY.value)
        )
        cause = consequence_cause_of(consequence.id)

        event = Event(
            id=self._new_event_id(),
            world_instance_id=instance.id,
            type=EventType.NPC_LEARNED,
            created_at=now,
            executed_at=now,
            actor=str(npc.id),
            target=information.key,
            cause=cause,
            payload={
                "npc_key": npc.key,
                "information_key": information.key,
                "claim": claim,
                "claim_type": claim_type.value,
                "source": source.value,
                "source_ref": cause,
                "confidence": confidence.value,
                "consequence_id": str(consequence.id),
                "effect": consequence.effect.value,
            },
            result="success",
        )
        instance.register_applied_event(event)
        uow.knowledge.add(
            Knowledge.record(
                id=new_knowledge_id(),
                world_instance_id=instance.id,
                subject_type=SubjectType.NPC,
                subject_id=str(npc.id),
                information_id=information.id,
                claim=claim,
                claim_type=claim_type,
                source=source,
                source_ref=cause,
                confidence=confidence,
                acquired_at=now,
            )
        )
        return event

    def _relational_shift(
        self, uow, instance, consequence: Consequence, now: datetime  # noqa: ANN001
    ) -> Event | None:
        payload = consequence.payload
        holder = SubjectRef(
            type=SubjectType(str(payload["holder_type"])), id=str(payload["holder_id"])
        )
        subject = SubjectRef(
            type=SubjectType(str(payload["subject_type"])), id=str(payload["subject_id"])
        )
        resolve_subject(uow, instance.id, holder)
        resolve_subject(uow, instance.id, subject)
        kind = RelationshipKind(str(payload["kind"]))
        direction = RelationshipDirection(str(payload["direction"]))

        existing = uow.relationships.find(instance.id, holder, subject, kind)
        current_level = existing.level if existing is not None else baseline_level(kind)
        new_level = step_level(kind, current_level, direction)
        if new_level is None:
            return None

        cause = consequence_cause_of(consequence.id)
        event = Event(
            id=self._new_event_id(),
            world_instance_id=instance.id,
            type=EventType.RELATIONSHIP_CHANGED,
            created_at=now,
            executed_at=now,
            actor=holder.id,
            target=subject.id,
            cause=cause,
            payload={
                "holder_type": holder.type.value,
                "holder_id": holder.id,
                "subject_type": subject.type.value,
                "subject_id": subject.id,
                "reason": cause,
                "changes": [
                    {
                        "kind": kind.value,
                        "from": current_level.value,
                        "to": new_level.value,
                    }
                ],
                "consequence_id": str(consequence.id),
                "effect": consequence.effect.value,
            },
            result="success",
        )
        instance.register_applied_event(event)
        relationship = existing or Relationship.create(
            id=new_relationship_id(),
            holder=holder,
            holder_instance_id=instance.id,
            subject=subject,
            subject_instance_id=instance.id,
            kind=kind,
            now=now,
        )
        relationship.apply(event)
        if existing is None:
            uow.relationships.add(relationship)
        else:
            uow.relationships.save(relationship)
        return event

    def _physical_status_change(
        self, uow, instance, consequence: Consequence, now: datetime  # noqa: ANN001
    ) -> Event | None:
        payload = consequence.payload
        npc = uow.npcs.get(instance.id, NpcId(str(payload["npc_id"])))
        target = NpcStatus(str(payload["status"]))
        if npc.status is target:
            return None

        cause = consequence_cause_of(consequence.id)
        event = Event(
            id=self._new_event_id(),
            world_instance_id=instance.id,
            type=EventType.NPC_STATUS_CHANGED,
            created_at=now,
            executed_at=now,
            actor=str(npc.id),
            target=str(npc.id),
            cause=cause,
            payload={
                "from": npc.status.value,
                "to": target.value,
                "consequence_id": str(consequence.id),
                "effect": consequence.effect.value,
            },
            result="success",
        )
        instance.register_applied_event(event)
        npc.apply(event)
        uow.npcs.save(npc)
        return event

    def _physical_relocate(
        self, uow, instance, consequence: Consequence, now: datetime  # noqa: ANN001
    ) -> Event | None:
        payload = consequence.payload
        npc = uow.npcs.get(instance.id, NpcId(str(payload["npc_id"])))
        npc.ensure_can_act()
        target = self._catalog.location(LocationKey(str(payload["to_location_key"])))
        from_key = npc.location_key
        if str(from_key) == str(target.key):
            return None
        if not self._catalog.is_connected(from_key, target.key):
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                f"location {target.key} is not connected to {from_key}",
            )

        cause = consequence_cause_of(consequence.id)
        event = Event(
            id=self._new_event_id(),
            world_instance_id=instance.id,
            type=EventType.NPC_MOVED,
            created_at=now,
            executed_at=now,
            actor=str(npc.id),
            target=str(target.key),
            cause=cause,
            payload={
                "from": str(from_key),
                "to": str(target.key),
                "consequence_id": str(consequence.id),
                "effect": consequence.effect.value,
            },
            result="success",
        )
        instance.register_applied_event(event)
        npc.apply(event)
        destination = uow.locations.get(instance.id, target.key)
        destination.apply(event)

        uow.npcs.save(npc)
        uow.locations.save(destination)
        return event
