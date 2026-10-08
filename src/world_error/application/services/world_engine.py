"""World Engine — точка входа application-слоя.

Каждый игровой запрос приходит сюда с обязательным ``world_instance_id``
(20_TECH_ARCHITECTURE_V1 §5) и проходит один путь: загрузка состояния →
создание EVENT → применение правил domain → запись состояния и события в одной
транзакции.

Это не God Object: движок не знает про Telegram, AI и SQL, не содержит правил
мира и не управляет чужими подсистемами. Правила живут в domain, хранение — за
портами (MASTER_SPEC §3.10, 20_TECH_ARCHITECTURE_V1 §29).

Новые действия (CREATE_CHARACTER / MOVE / INSPECT) возвращают ``ActionResult``:
игровая ошибка — часть результата, а не только исключение.

Инстанс-события коммита 1 (`create_instance`, `advance_tick`, `change_status`)
сохраняют прежнюю сигнатуру и не переписываются.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from world_error.application.action_result import ActionResult
from world_error.application.ai.dialogue import NpcDialogueProvider
from world_error.application.ai.npc_context_builder import NpcDialogueContextBuilder
from world_error.application.ai.registry import resolve_handler
from world_error.application.ai.providers.npc_template import TemplateNpcDialogueProvider
from world_error.application.commands.apply_significant_action import (
    ApplySignificantActionCommand,
    ApplySignificantActionHandler,
)
from world_error.application.commands.add_case_note import AddCaseNoteCommand, AddCaseNoteHandler
from world_error.application.commands.add_case_question import (
    AddCaseQuestionCommand,
    AddCaseQuestionHandler,
)
from world_error.application.commands.begin_travel import BeginTravelCommand, BeginTravelHandler
from world_error.application.commands.change_relationship import (
    ChangeRelationshipCommand,
    ChangeRelationshipHandler,
)
from world_error.application.commands.change_faction_status import (
    ChangeFactionStatusCommand,
    ChangeFactionStatusHandler,
)
from world_error.application.commands.drop_item import DropItemCommand, DropItemHandler
from world_error.application.commands.kill_character import (
    KillCharacterCommand,
    KillCharacterHandler,
)
from world_error.application.commands.leave_legacy_document import (
    LeaveLegacyDocumentCommand,
    LeaveLegacyDocumentHandler,
)
from world_error.application.commands.inspect_legacy_document import (
    InspectLegacyDocumentCommand,
    InspectLegacyDocumentHandler,
)
from world_error.application.commands.cancel_consequence import (
    CancelConsequenceCommand,
    CancelConsequenceHandler,
)
from world_error.application.commands.close_case import CloseCaseCommand, CloseCaseHandler
from world_error.application.commands.create_theory import CreateTheoryCommand, CreateTheoryHandler
from world_error.application.commands.create_character import (
    CreateCharacterCommand,
    CreateCharacterHandler,
)
from world_error.application.commands.create_world_instance import (
    CreateWorldInstanceCommand,
    CreateWorldInstanceHandler,
)
from world_error.application.commands.inspect_information import (
    InspectInformationCommand,
    InspectInformationHandler,
)
from world_error.application.commands.link_evidence import LinkEvidenceCommand, LinkEvidenceHandler
from world_error.application.commands.link_theory_evidence import (
    LinkTheoryEvidenceCommand,
    LinkTheoryEvidenceHandler,
)
from world_error.application.commands.mark_contradiction import (
    MarkContradictionCommand,
    MarkContradictionHandler,
)
from world_error.application.commands.mark_suspect import MarkSuspectCommand, MarkSuspectHandler
from world_error.application.commands.move_character import (
    MoveCharacterCommand,
    MoveCharacterHandler,
)
from world_error.application.commands.npc_change_status import (
    NpcChangeStatusCommand,
    NpcChangeStatusHandler,
)
from world_error.application.commands.npc_learn import NpcLearnCommand, NpcLearnHandler
from world_error.application.commands.npc_move import NpcMoveCommand, NpcMoveHandler
from world_error.application.commands.npc_observe_information import (
    NpcObserveInformationCommand,
    NpcObserveInformationHandler,
)
from world_error.application.commands.record_time_point import (
    RecordTimePointCommand,
    RecordTimePointHandler,
)
from world_error.application.commands.schedule_consequence import (
    ScheduleConsequenceCommand,
    ScheduleConsequenceHandler,
)
from world_error.application.commands.transform_consequence import (
    TransformConsequenceCommand,
    TransformConsequenceHandler,
)
from world_error.application.commands.take_item import TakeItemCommand, TakeItemHandler
from world_error.application.commands.trade_items import TradeItemsCommand, TradeItemsHandler
from world_error.application.commands.schedule_event import ScheduleEventCommand, ScheduleEventHandler
from world_error.application.commands.share_knowledge import (
    ShareKnowledgeCommand,
    ShareKnowledgeHandler,
)
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.application.queries.location_view import LocationView, LocationViewQuery
from world_error.application.queries.faction_view import FactionView, FactionViewQuery
from world_error.application.queries.inventory_view import InventoryView, InventoryViewQuery
from world_error.application.queries.case_view import (
    CaseEvidenceView,
    CaseNoteView,
    CaseSuspectView,
    CaseTheoryView,
    CaseView,
    CaseViewQuery,
)
from world_error.application.services.consequence_engine import (
    ConsequenceEngine,
    PumpOutcome,
)
from world_error.application.services.scheduled_event_engine import (
    ScheduledEventEngine,
    ScheduledPumpOutcome,
)
from world_error.domain.consequences.consequence import Consequence, ConsequenceTrigger
from world_error.domain.consequences.vocabulary import (
    ConsequenceEffect,
    ConsequenceScale,
    ConsequenceType,
    ConsequenceVisibility,
)
from world_error.domain.characters.character import Character
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.factions.faction import Faction, FactionStatus
from world_error.domain.investigations.case import (
    CaseEvidenceRelevance,
    CaseNoteVisibility,
    CaseSuspectStatus,
    CaseTheoryConfidence,
    CaseTheoryEvidenceStance,
    CaseVisibility,
)
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.npcs.npc import Npc, NpcDefinition, NpcStatus
from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipDirection,
    RelationshipKind,
    RelationshipVisibility,
    SubjectRef,
)
from world_error.domain.relationships.rules import SignificantAction
from world_error.domain.shared.kernel import (
    CharacterId,
    CaseEvidenceLinkId,
    CaseId,
    CaseTheoryId,
    Clock,
    ConsequenceId,
    DomainError,
    ErrorCode,
    EventId,
    FactionId,
    ItemId,
    InformationId,
    KnowledgeId,
    LocationKey,
    LegacyDocumentId,
    NpcId,
    ScheduledEventId,
    SystemClock,
    WorldInstanceId,
    new_event_id,
)
from world_error.domain.world.instance import InstanceEnvironment, InstanceLifecycle, WorldInstance
from world_error.domain.time.scheduled_event import ScheduledEvent, ScheduledTriggerKind
from world_error.domain.time.time_point import TimePoint
from world_error.domain.time.action_cost import CostTicks

DEFAULT_SEED_BITS = 63


class _PumpedHandler:
    """Прозрачная обёртка обработчика: после успешного действия идёт насос.

    Обёртка нужна, чтобы не переписывать методы движка: все они вызывают
    ``handler.handle(command)`` и не знают о последствиях.
    """

    def __init__(self, handle: Callable[[Any], ActionResult]) -> None:
        self._handle = handle

    def handle(self, command: Any) -> ActionResult:
        return self._handle(command)


@dataclass(frozen=True, slots=True)
class WorldPumpOutcome:
    scheduled: ScheduledPumpOutcome
    consequences: PumpOutcome
    event_ids: tuple[EventId, ...]
    steps: int
    limit_reached: bool

    @property
    def changed(self) -> bool:
        return self.scheduled.changed or self.consequences.changed or bool(self.event_ids)


class WorldEngine:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        catalog: ContentCatalog,
        clock: Clock | None = None,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        npc_dialogue_provider: NpcDialogueProvider | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog
        self._clock = clock or SystemClock()
        self._new_event_id = new_event_id_factory
        self._npc_context_builder = NpcDialogueContextBuilder(self)
        self._npc_dialogue_provider = npc_dialogue_provider or TemplateNpcDialogueProvider()
        self._npc_dialogue_fallback = TemplateNpcDialogueProvider()
        self._create_world_instance = CreateWorldInstanceHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._create_character = CreateCharacterHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._kill_character = KillCharacterHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._leave_legacy_document = LeaveLegacyDocumentHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._inspect_legacy_document = InspectLegacyDocumentHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._move_character = MoveCharacterHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._begin_travel = BeginTravelHandler(
            uow_factory=uow_factory,
            catalog=catalog,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._inspect_information = InspectInformationHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._share_knowledge = ShareKnowledgeHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._location_view = LocationViewQuery(uow_factory=uow_factory, catalog=catalog)
        self._faction_view = FactionViewQuery(uow_factory=uow_factory, catalog=catalog)
        self._inventory_view = InventoryViewQuery(uow_factory=uow_factory, catalog=catalog)
        self._case_view = CaseViewQuery(uow_factory=uow_factory, catalog=catalog)
        self._take_item = TakeItemHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._drop_item = DropItemHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._trade_items = TradeItemsHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._link_evidence = LinkEvidenceHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._create_theory = CreateTheoryHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._link_theory_evidence = LinkTheoryEvidenceHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._mark_contradiction = MarkContradictionHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._mark_suspect = MarkSuspectHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._add_case_note = AddCaseNoteHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._add_case_question = AddCaseQuestionHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._close_case = CloseCaseHandler(
            uow_factory=uow_factory,
            catalog=catalog,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._change_relationship = ChangeRelationshipHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._change_faction_status = ChangeFactionStatusHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._apply_significant_action = ApplySignificantActionHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._npc_move = NpcMoveHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._npc_learn = NpcLearnHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._npc_observe = NpcObserveInformationHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
            new_event_id_factory=self._new_event_id,
        )
        self._npc_change_status = NpcChangeStatusHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._schedule_consequence = ScheduleConsequenceHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._cancel_consequence = CancelConsequenceHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._transform_consequence = TransformConsequenceHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._schedule_event_command = ScheduleEventHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._record_time_point = RecordTimePointHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._scheduled_events = ScheduledEventEngine(
            uow_factory=uow_factory,
            catalog=catalog,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )
        self._consequences = ConsequenceEngine(
            uow_factory=uow_factory,
            catalog=catalog,
            schedule_handler=self._schedule_consequence,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )

        # Каждое действие-команда после успеха прогоняет насос последствий: если
        # незакрытых последствий нет, поведение не меняется вообще.
        self._create_character = self._pumped(self._create_character)
        self._kill_character = self._pumped(self._kill_character)
        self._leave_legacy_document = self._pumped(self._leave_legacy_document)
        self._inspect_legacy_document = self._pumped(self._inspect_legacy_document)
        self._move_character = self._pumped(self._move_character)
        self._begin_travel = self._pumped(self._begin_travel, pump_after=False)
        self._inspect_information = self._pumped(self._inspect_information)
        self._share_knowledge = self._pumped(self._share_knowledge)
        self._npc_move = self._pumped(self._npc_move)
        self._npc_learn = self._pumped(self._npc_learn)
        self._npc_observe = self._pumped(self._npc_observe)
        self._npc_change_status = self._pumped(self._npc_change_status)
        self._change_relationship = self._pumped(self._change_relationship)
        self._change_faction_status = self._pumped(self._change_faction_status)
        self._take_item = self._pumped(self._take_item)
        self._drop_item = self._pumped(self._drop_item)
        self._trade_items = self._pumped(self._trade_items)
        self._link_evidence = self._pumped(self._link_evidence)
        self._create_theory = self._pumped(self._create_theory)
        self._link_theory_evidence = self._pumped(self._link_theory_evidence)
        self._mark_contradiction = self._pumped(self._mark_contradiction)
        self._mark_suspect = self._pumped(self._mark_suspect)
        self._add_case_note = self._pumped(self._add_case_note)
        self._add_case_question = self._pumped(self._add_case_question)
        self._close_case = self._pumped(self._close_case)
        self._apply_significant_action = self._pumped(self._apply_significant_action)
        self._schedule_consequence = self._pumped(self._schedule_consequence)
        self._cancel_consequence = self._pumped(self._cancel_consequence)
        self._transform_consequence = self._pumped(self._transform_consequence)
        self._schedule_event_command = self._pumped(self._schedule_event_command)
        self._record_time_point = self._pumped(self._record_time_point)

    # --- насос последствий --------------------------------------------------

    def _pumped(self, handler: Any, *, pump_after: bool = True) -> "_PumpedHandler":
        def handle(command: Any) -> ActionResult:
            before = self._pump_world(command.world_instance_id)
            if before.limit_reached:
                return ActionResult.failure(
                    "WORLD_TIME",
                    DomainError(
                        ErrorCode.CASCADE_LIMIT,
                        "consequence cascade limit reached "
                        f"({self._consequences.max_cascade_steps} steps)",
                    ),
                )
            result = handler.handle(command)
            if not result.ok:
                return result
            if not pump_after:
                return result
            return self._pump_into_result(result, command.world_instance_id)

        return _PumpedHandler(handle)

    def _pump_into_result(
        self, result: ActionResult, world_instance_id: WorldInstanceId
    ) -> ActionResult:
        outcome = self._pump_world(world_instance_id)
        if outcome.limit_reached:
            # M1: уже применённые последствия остаются применёнными, отката нет.
            return ActionResult.failure(
                result.action,
                DomainError(
                    ErrorCode.CASCADE_LIMIT,
                    "consequence cascade limit reached "
                    f"({self._consequences.max_cascade_steps} steps)",
                ),
            )
        if not outcome.changed:
            return result
        payload = dict(result.payload)
        if outcome.scheduled.applied:
            payload["scheduled_events_applied"] = len(outcome.scheduled.applied)
        if outcome.consequences.applied:
            payload["consequences_applied"] = len(outcome.consequences.applied)
        if outcome.consequences.failed:
            payload["consequences_failed"] = len(outcome.consequences.failed)
        if outcome.consequences.failed_rules:
            payload["consequence_rules_failed"] = outcome.consequences.failed_rules
        return ActionResult.success(
            result.action,
            event_ids=tuple(result.event_ids) + outcome.event_ids,
            payload=payload,
        )

    def _pump_world(self, world_instance_id: WorldInstanceId) -> WorldPumpOutcome:
        instance = self.get_instance(world_instance_id)
        if instance.lifecycle is not InstanceLifecycle.ACTIVE:
            return WorldPumpOutcome(
                scheduled=ScheduledPumpOutcome(),
                consequences=PumpOutcome(),
                event_ids=(),
                steps=0,
                limit_reached=False,
            )

        max_steps = self._consequences.max_cascade_steps
        steps = 0
        scheduled_ids: list[ScheduledEventId] = []
        scheduled_failed_ids: list[ScheduledEventId] = []
        consequence_ids = []
        failed_ids = []
        scheduled_event_ids: list[EventId] = []
        consequence_event_ids: list[EventId] = []
        event_ids: list[EventId] = []
        failed_rules: list[str] = []
        limit_reached = False

        while True:
            remaining = max_steps - steps
            scheduled = self._scheduled_events.pump(
                world_instance_id, max_steps=max(0, remaining)
            )
            scheduled_ids.extend(scheduled.applied)
            scheduled_failed_ids.extend(scheduled.failed)
            event_ids.extend(scheduled.event_ids)
            scheduled_event_ids.extend(scheduled.event_ids)
            steps += scheduled.steps

            consequences = self._consequences.pump(
                world_instance_id, max_steps=max(0, max_steps - steps)
            )
            consequence_ids.extend(consequences.applied)
            failed_ids.extend(consequences.failed)
            event_ids.extend(consequences.event_ids)
            consequence_event_ids.extend(consequences.event_ids)
            failed_rules.extend(consequences.failed_rules)
            steps += consequences.steps

            if scheduled.limit_reached or consequences.limit_reached:
                limit_reached = True
                break
            if steps >= max_steps:
                limit_reached = self._scheduled_events.has_due(
                    world_instance_id
                ) or self._consequences.has_due(world_instance_id)
                break
            if not (
                scheduled.changed
                or consequences.applied
                or consequences.failed
                or consequences.event_ids
            ):
                break

        return WorldPumpOutcome(
            scheduled=ScheduledPumpOutcome(
                applied=tuple(scheduled_ids),
                failed=tuple(scheduled_failed_ids),
                event_ids=tuple(scheduled_event_ids),
                limit_reached=limit_reached,
            ),
            consequences=PumpOutcome(
                applied=tuple(consequence_ids),
                failed=tuple(failed_ids),
                event_ids=tuple(consequence_event_ids),
                failed_rules=tuple(dict.fromkeys(failed_rules)),
                limit_reached=limit_reached,
                steps=steps,
            ),
            event_ids=tuple(dict.fromkeys(event_ids)),
            steps=steps,
            limit_reached=limit_reached,
        )

    # --- команды коммита 1 (инстанс-события) -------------------------------

    def create_instance(
        self,
        telegram_chat_id: int,
        *,
        seed: int | None = None,
        environment: InstanceEnvironment = InstanceEnvironment.DEV,
        actor: str = "system",
    ) -> WorldInstance:
        """Создать WORLD INSTANCE и материализовать instance-состояние из контента.

        ``seed`` хранится в инстансе: он нужен, чтобы случайность в будущем
        была воспроизводимой (20_TECH_ARCHITECTURE_V1 §25).
        """
        if seed is None:
            seed = secrets.randbits(DEFAULT_SEED_BITS)
        return self._create_world_instance.handle(
            CreateWorldInstanceCommand(
                telegram_chat_id=telegram_chat_id,
                seed=seed,
                environment=environment,
                actor=actor,
            )
        )

    def advance_tick(self, world_instance_id: WorldInstanceId, *, cause: str = "manual") -> WorldInstance:
        """Продвинуть мировой тик на 1 и записать ``WORLD_TICK_ADVANCED``.

        ВРЕМЕННЫЙ механизм коммита 1 "Фундамент": он нужен только чтобы
        проверить event-driven переход состояния и восстановление после
        перезапуска процесса без игрового контента. Игровые действия коммита 2
        тик не через него двигают: ``MOVE`` и ``INSPECT`` увеличивают
        ``world_tick`` как часть обработки своего события.

        После продвижения тика запускается насос последствий: отложенные
        последствия, срок которых наступил, применяются. Если каскад упёрся в
        лимит, поднимается ``CASCADE_LIMIT`` — уже применённые последствия при
        этом остаются применёнными (отката нет).
        """
        instance = self._apply(
            world_instance_id,
            EventType.WORLD_TICK_ADVANCED,
            cause=cause,
            target=str(world_instance_id),
            payload_factory=lambda instance: {
                "from_tick": instance.state.world_tick,
                "to_tick": instance.state.world_tick + 1,
            },
        )
        outcome = self._pump_world(world_instance_id)
        if outcome.limit_reached:
            raise DomainError(
                ErrorCode.CASCADE_LIMIT,
                "consequence cascade limit reached "
                f"({self._consequences.max_cascade_steps} steps)",
            )
        return instance

    def change_status(
        self,
        world_instance_id: WorldInstanceId,
        *,
        to: InstanceLifecycle | str,
        cause: str = "manual",
    ) -> WorldInstance:
        """Сменить жизненный цикл инстанса.

        Идёт через тот же Unit of Work, что и остальные изменения: админских
        путей в обход транзакции нет.
        """
        target = InstanceLifecycle(to)
        instance = self._apply(
            world_instance_id,
            EventType.WORLD_INSTANCE_STATUS_CHANGED,
            cause=cause,
            target=str(world_instance_id),
            payload_factory=lambda instance: {"from": instance.lifecycle.value, "to": target.value},
        )
        outcome = self._pump_world(world_instance_id)
        if outcome.limit_reached:
            raise DomainError(ErrorCode.CASCADE_LIMIT, "world pump cascade limit reached")
        return instance

    def handle_intent(
        self,
        world_instance_id: WorldInstanceId,
        actor_id: CharacterId,
        intent,
    ) -> ActionResult:  # noqa: ANN001
        resolved = resolve_handler(intent.type)
        if resolved is None:
            return ActionResult.failure(
                "HANDLE_INTENT",
                DomainError(ErrorCode.INVALID_ACTION, f"unsupported player intent: {intent.type}"),
            )
        if intent.actor_id != actor_id:
            return ActionResult.failure(
                "HANDLE_INTENT",
                DomainError(ErrorCode.NOT_ALLOWED, "intent actor does not match request actor"),
            )

        parameters = dict(intent.params)
        parameters[resolved.actor_param] = actor_id
        if intent.target is not None and resolved.target_param is not None:
            parameters[resolved.target_param] = intent.target
        handler = getattr(self, resolved.method_name)
        return handler(world_instance_id, **parameters)

    # --- команды коммита 2 -------------------------------------------------

    def create_character(
        self,
        world_instance_id: WorldInstanceId,
        *,
        player_id: str,
        name: str,
        location_key: LocationKey | None = None,
        actor: str = "system",
    ) -> ActionResult:
        return self._create_character.handle(
            CreateCharacterCommand(
                world_instance_id=world_instance_id,
                player_id=player_id,
                name=name,
                location_key=location_key,
                actor=actor,
            )
        )

    def spawn_new_character(
        self,
        world_instance_id: WorldInstanceId,
        *,
        player_id: str,
        name: str,
        location_key: LocationKey | None = None,
    ) -> ActionResult:
        """Spawn from the world's normal start rules; no predecessor is stored."""
        return self.create_character(
            world_instance_id,
            player_id=player_id,
            name=name,
            location_key=location_key,
        )

    def kill_character(
        self,
        world_instance_id: WorldInstanceId,
        character_id: CharacterId,
        *,
        cause_event_id: EventId,
        death_event_id: EventId | None = None,
        actor: str = "world",
    ) -> ActionResult:
        return self._kill_character.handle(
            KillCharacterCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                cause_event_id=cause_event_id,
                death_event_id=death_event_id,
                actor=actor,
            )
        )

    def die_character(
        self,
        world_instance_id: WorldInstanceId,
        character_id: CharacterId,
        *,
        cause_event_id: EventId,
        death_event_id: EventId | None = None,
    ) -> ActionResult:
        return self.kill_character(
            world_instance_id,
            character_id,
            cause_event_id=cause_event_id,
            death_event_id=death_event_id,
        )

    def leave_legacy_document(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        document_key: str,
        content: str,
    ) -> ActionResult:
        return self._leave_legacy_document.handle(
            LeaveLegacyDocumentCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                document_key=document_key,
                content=content,
            )
        )

    def inspect_legacy_document(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        document_id: LegacyDocumentId,
    ) -> ActionResult:
        return self._inspect_legacy_document.handle(
            InspectLegacyDocumentCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                document_id=document_id,
            )
        )

    def move_character(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        to_location_key: LocationKey,
        cost_ticks: CostTicks | int | None = None,
        cause: str = "move",
    ) -> ActionResult:
        return self._move_character.handle(
            MoveCharacterCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                to_location_key=to_location_key,
                cost_ticks=cost_ticks,
                cause=cause,
            )
        )

    def begin_travel(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        to_location_key: LocationKey,
        cost_ticks: CostTicks,
        idempotency_key: str,
    ) -> ActionResult:
        """Start a delayed, scheduled arrival; the character stays at origin until due."""
        return self._begin_travel.handle(
            BeginTravelCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                to_location_key=str(to_location_key),
                cost_ticks=cost_ticks,
                idempotency_key=idempotency_key,
            )
        )

    def inspect_information(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        target_key: str,
        cost_ticks: CostTicks | int | None = None,
        cause: str = "inspect",
    ) -> ActionResult:
        return self._inspect_information.handle(
            InspectInformationCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                target_key=target_key,
                cost_ticks=cost_ticks,
                cause=cause,
            )
        )

    def share_knowledge(
        self,
        world_instance_id: WorldInstanceId,
        *,
        sharer_id: CharacterId,
        receiver_id: CharacterId,
        information_key: str,
        cause: str = "share",
    ) -> ActionResult:
        """Передать знание другому персонажу в той же локации (SHARE).

        Каталог контента сюда не передаётся: claim берётся из знания sharer'а,
        поэтому truth в этот путь попасть не может.
        """
        return self._share_knowledge.handle(
            ShareKnowledgeCommand(
                world_instance_id=world_instance_id,
                sharer_id=sharer_id,
                receiver_id=receiver_id,
                information_key=information_key,
                cause=cause,
            )
        )

    def take_item(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        item_id: ItemId,
        quantity: int | None = None,
    ) -> ActionResult:
        return self._take_item.handle(
            TakeItemCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                item_id=item_id,
                quantity=quantity,
            )
        )

    def drop_item(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        item_id: ItemId,
        quantity: int | None = None,
    ) -> ActionResult:
        return self._drop_item.handle(
            DropItemCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                item_id=item_id,
                quantity=quantity,
            )
        )

    def trade_items(
        self,
        world_instance_id: WorldInstanceId,
        *,
        initiator_id: CharacterId,
        counterparty_id: CharacterId,
        offered_item_id: ItemId,
        offered_quantity: int | None = None,
        requested_item_id: ItemId | None = None,
        requested_quantity: int | None = None,
    ) -> ActionResult:
        return self._trade_items.handle(
            TradeItemsCommand(
                world_instance_id=world_instance_id,
                initiator_id=initiator_id,
                counterparty_id=counterparty_id,
                offered_item_id=offered_item_id,
                offered_quantity=offered_quantity,
                requested_item_id=requested_item_id,
                requested_quantity=requested_quantity,
            )
        )

    def give_item(
        self,
        world_instance_id: WorldInstanceId,
        *,
        giver_id: CharacterId,
        receiver_id: CharacterId,
        item_id: ItemId,
        quantity: int | None = None,
    ) -> ActionResult:
        """One-way GIVE uses ITEM_TRANSFERRED without a requested counter-item."""
        return self.trade_items(
            world_instance_id,
            initiator_id=giver_id,
            counterparty_id=receiver_id,
            offered_item_id=item_id,
            offered_quantity=quantity,
        )

    def link_evidence(
        self,
        world_instance_id: WorldInstanceId,
        *,
        case_id: CaseId,
        actor_id: CharacterId,
        information_id: InformationId,
        relevance: CaseEvidenceRelevance | None = None,
    ) -> ActionResult:
        return self._link_evidence.handle(
            LinkEvidenceCommand(
                world_instance_id=world_instance_id,
                case_id=case_id,
                actor_id=actor_id,
                information_id=information_id,
                relevance=relevance,
            )
        )

    def create_theory(
        self,
        world_instance_id: WorldInstanceId,
        *,
        case_id: CaseId,
        author_id: CharacterId,
        claim: str,
        confidence: CaseTheoryConfidence = CaseTheoryConfidence.SPECULATIVE,
        visibility: CaseVisibility = CaseVisibility.PRIVATE,
    ) -> ActionResult:
        return self._create_theory.handle(
            CreateTheoryCommand(
                world_instance_id=world_instance_id,
                case_id=case_id,
                author_id=author_id,
                claim=claim,
                confidence=confidence,
                visibility=visibility,
            )
        )

    def link_theory_evidence(
        self,
        world_instance_id: WorldInstanceId,
        *,
        case_id: CaseId,
        actor_id: CharacterId,
        theory_id: CaseTheoryId,
        evidence_link_id: CaseEvidenceLinkId,
        stance: CaseTheoryEvidenceStance,
    ) -> ActionResult:
        return self._link_theory_evidence.handle(
            LinkTheoryEvidenceCommand(
                world_instance_id=world_instance_id,
                case_id=case_id,
                actor_id=actor_id,
                theory_id=theory_id,
                evidence_link_id=evidence_link_id,
                stance=stance,
            )
        )

    def mark_contradiction(
        self,
        world_instance_id: WorldInstanceId,
        *,
        case_id: CaseId,
        actor_id: CharacterId,
        evidence_a_id: CaseEvidenceLinkId,
        evidence_b_id: CaseEvidenceLinkId,
        note: str,
    ) -> ActionResult:
        return self._mark_contradiction.handle(
            MarkContradictionCommand(
                world_instance_id=world_instance_id,
                case_id=case_id,
                actor_id=actor_id,
                evidence_a_id=evidence_a_id,
                evidence_b_id=evidence_b_id,
                note=note,
            )
        )

    def mark_suspect(
        self,
        world_instance_id: WorldInstanceId,
        *,
        case_id: CaseId,
        actor_id: CharacterId,
        subject_type: SubjectType,
        subject_id: str,
        reason: str,
        status: CaseSuspectStatus = CaseSuspectStatus.SUSPECTED,
    ) -> ActionResult:
        return self._mark_suspect.handle(
            MarkSuspectCommand(
                world_instance_id=world_instance_id,
                case_id=case_id,
                actor_id=actor_id,
                subject_type=subject_type,
                subject_id=subject_id,
                reason=reason,
                status=status,
            )
        )

    def add_case_note(
        self,
        world_instance_id: WorldInstanceId,
        *,
        case_id: CaseId,
        author_id: CharacterId,
        text: str,
        visibility: CaseNoteVisibility = CaseNoteVisibility.PRIVATE,
    ) -> ActionResult:
        return self._add_case_note.handle(
            AddCaseNoteCommand(
                world_instance_id=world_instance_id,
                case_id=case_id,
                author_id=author_id,
                text=text,
                visibility=visibility,
            )
        )

    def add_case_question(
        self,
        world_instance_id: WorldInstanceId,
        *,
        case_id: CaseId,
        added_by: CharacterId,
        text: str,
    ) -> ActionResult:
        return self._add_case_question.handle(
            AddCaseQuestionCommand(
                world_instance_id=world_instance_id,
                case_id=case_id,
                added_by=added_by,
                text=text,
            )
        )

    def close_case(
        self, world_instance_id: WorldInstanceId, *, case_id: CaseId, actor_id: CharacterId
    ) -> ActionResult:
        return self._close_case.handle(
            CloseCaseCommand(
                world_instance_id=world_instance_id,
                case_id=case_id,
                actor_id=actor_id,
            )
        )

    # --- команды NPC (коммит 4) --------------------------------------------

    def npc_move(
        self,
        world_instance_id: WorldInstanceId,
        *,
        npc_id: NpcId,
        to_location_key: LocationKey,
        cause: str = "npc_move",
    ) -> ActionResult:
        return self._npc_move.handle(
            NpcMoveCommand(
                world_instance_id=world_instance_id,
                npc_id=npc_id,
                to_location_key=to_location_key,
                cause=cause,
            )
        )

    def npc_learn(
        self,
        world_instance_id: WorldInstanceId,
        *,
        npc_id: NpcId,
        information_key: str,
        claim_type: ClaimType = ClaimType.FACT,
        source: KnowledgeSource = KnowledgeSource.OBSERVATION,
        confidence: KnowledgeConfidence = KnowledgeConfidence.LIKELY,
        claim: str | None = None,
        source_ref: str | None = None,
        cause: str = "npc_learn",
    ) -> ActionResult:
        """Передать NPC информацию. ``claim`` по умолчанию — из контента, truth не читается."""
        return self._npc_learn.handle(
            NpcLearnCommand(
                world_instance_id=world_instance_id,
                npc_id=npc_id,
                information_key=information_key,
                claim_type=claim_type,
                source=source,
                confidence=confidence,
                claim=claim,
                source_ref=source_ref,
                cause=cause,
            )
        )

    def npc_observe_information(
        self,
        world_instance_id: WorldInstanceId,
        *,
        npc_id: NpcId,
        information_key: str,
        cause: str = "npc_observe",
    ) -> ActionResult:
        """NPC сам находит объект: мир отмечает обнаружение, NPC получает знание."""
        return self._npc_observe.handle(
            NpcObserveInformationCommand(
                world_instance_id=world_instance_id,
                npc_id=npc_id,
                information_key=information_key,
                cause=cause,
            )
        )

    def npc_change_status(
        self,
        world_instance_id: WorldInstanceId,
        *,
        npc_id: NpcId,
        to_status: NpcStatus | str,
        cause: str = "npc_status",
    ) -> ActionResult:
        return self._npc_change_status.handle(
            NpcChangeStatusCommand(
                world_instance_id=world_instance_id,
                npc_id=npc_id,
                to_status=to_status,
                cause=cause,
            )
        )

    def talk_to_npc(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        npc_id: NpcId,
        message: str,
    ) -> ActionResult:
        action = "TALK_TO_NPC"
        try:
            character = self.get_character(world_instance_id, character_id)
            character.ensure_can_act()
            npc = self.get_npc(world_instance_id, npc_id)
            npc.ensure_can_act()
            if character.location_key != npc.location_key:
                raise DomainError(
                    ErrorCode.NOT_ALLOWED,
                    f"npc {npc.id} is not at character location",
                )
            context = self._npc_context_builder.build_npc_dialogue_context(
                world_instance_id, npc_id
            )
        except DomainError as exc:
            return ActionResult.failure(action, exc)

        try:
            reply = self._npc_dialogue_provider.generate_reply(context, message)
        except NotImplementedError:
            reply = None
        if reply is None or not reply.strip():
            reply = self._npc_dialogue_fallback.generate_reply(context, message)
        return ActionResult.success(
            action,
            payload={"npc_id": str(npc.id), "npc_key": npc.key, "reply": reply},
        )

    # --- отношения (коммит 5) ----------------------------------------------

    def change_relationship(
        self,
        world_instance_id: WorldInstanceId,
        *,
        holder: SubjectRef,
        subject: SubjectRef,
        kind: RelationshipKind,
        direction: RelationshipDirection,
        visibility: RelationshipVisibility | None = None,
        reason: str = "manual",
    ) -> ActionResult:
        """Сдвинуть отношение holder → subject на одну ступень по лестнице вида."""
        return self._change_relationship.handle(
            ChangeRelationshipCommand(
                world_instance_id=world_instance_id,
                holder=holder,
                subject=subject,
                kind=kind,
                direction=direction,
                visibility=visibility,
                reason=reason,
            )
        )

    def change_faction_status(
        self,
        world_instance_id: WorldInstanceId,
        *,
        faction_id: FactionId,
        to_status: FactionStatus | str,
    ) -> ActionResult:
        return self._change_faction_status.handle(
            ChangeFactionStatusCommand(
                world_instance_id=world_instance_id,
                faction_id=faction_id,
                to_status=to_status,
            )
        )

    def apply_significant_action(
        self,
        world_instance_id: WorldInstanceId,
        *,
        actor: SubjectRef,
        holder: SubjectRef,
        action: SignificantAction,
    ) -> ActionResult:
        """Значимое действие: holder меняет своё отношение к actor по правилу домена."""
        return self._apply_significant_action.handle(
            ApplySignificantActionCommand(
                world_instance_id=world_instance_id,
                actor=actor,
                holder=holder,
                action=action,
            )
        )

    # --- последствия (коммит 6) --------------------------------------------

    def schedule_consequence(
        self,
        world_instance_id: WorldInstanceId,
        *,
        cause_event_ids: Sequence[EventId],
        type: ConsequenceType,
        scale: ConsequenceScale,
        visibility: ConsequenceVisibility,
        trigger: ConsequenceTrigger,
        effect: ConsequenceEffect,
        payload: Mapping[str, Any] | None = None,
        rule_key: str | None = None,
    ) -> ActionResult:
        """Запланировать последствие. Причина обязательна: последствий без причины нет."""
        return self._schedule_consequence.handle(
            ScheduleConsequenceCommand(
                world_instance_id=world_instance_id,
                cause_event_ids=tuple(cause_event_ids),
                type=type,
                scale=scale,
                visibility=visibility,
                trigger=trigger,
                effect=effect,
                payload=dict(payload or {}),
                rule_key=rule_key,
            )
        )

    def cancel_consequence(
        self,
        world_instance_id: WorldInstanceId,
        consequence_id: ConsequenceId,
        *,
        actor: str = "system",
    ) -> ActionResult:
        return self._cancel_consequence.handle(
            CancelConsequenceCommand(
                world_instance_id=world_instance_id,
                consequence_id=consequence_id,
                actor=actor,
            )
        )

    def transform_consequence(
        self,
        world_instance_id: WorldInstanceId,
        consequence_id: ConsequenceId,
        *,
        type: ConsequenceType,
        scale: ConsequenceScale,
        visibility: ConsequenceVisibility,
        trigger: ConsequenceTrigger,
        effect: ConsequenceEffect,
        payload: Mapping[str, Any],
        actor: str = "system",
    ) -> ActionResult:
        return self._transform_consequence.handle(
            TransformConsequenceCommand(
                world_instance_id=world_instance_id,
                consequence_id=consequence_id,
                type=type,
                scale=scale,
                visibility=visibility,
                trigger=trigger,
                effect=effect,
                payload=dict(payload),
                actor=actor,
            )
        )

    def schedule_event(
        self,
        world_instance_id: WorldInstanceId,
        *,
        cause_event_id: EventId,
        event_key: str,
        idempotency_key: str,
        trigger_kind: ScheduledTriggerKind | str,
        payload: Mapping[str, Any] | None = None,
        due_tick: int | None = None,
        due_time: datetime | None = None,
        trigger_event_type: EventType | str | None = None,
        actor: str = "system",
    ) -> ActionResult:
        return self._schedule_event_command.handle(
            ScheduleEventCommand(
                world_instance_id=world_instance_id,
                cause_event_id=cause_event_id,
                event_key=event_key,
                idempotency_key=idempotency_key,
                trigger_kind=ScheduledTriggerKind(trigger_kind),
                payload=dict(payload or {}),
                due_tick=due_tick,
                due_time=due_time,
                trigger_event_type=(
                    None if trigger_event_type is None else EventType(trigger_event_type)
                ),
                actor=actor,
            )
        )

    def record_time_point(
        self, world_instance_id: WorldInstanceId, *, time_point: TimePoint
    ) -> ActionResult:
        return self._record_time_point.handle(
            RecordTimePointCommand(world_instance_id=world_instance_id, time_point=time_point)
        )

    def pump_time(self, world_instance_id: WorldInstanceId) -> WorldPumpOutcome:
        return self._pump_world(world_instance_id)

    def pump_consequences(self, world_instance_id: WorldInstanceId) -> PumpOutcome:
        """Прогнать оба насоса с общим лимитом (тесты, диагностика)."""
        return self._pump_world(world_instance_id).consequences

    def pump_scheduled_events(self, world_instance_id: WorldInstanceId) -> ScheduledPumpOutcome:
        """Прогнать общий pump cycle и вернуть результат scheduled events."""
        return self._pump_world(world_instance_id).scheduled

    def get_consequence(
        self, world_instance_id: WorldInstanceId, consequence_id: ConsequenceId
    ) -> Consequence:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return uow.consequences.get(world_instance_id, consequence_id)

    def get_scheduled_event(
        self, world_instance_id: WorldInstanceId, scheduled_event_id: ScheduledEventId
    ) -> ScheduledEvent:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return uow.scheduled_events.get(world_instance_id, scheduled_event_id)

    def list_scheduled_events(
        self, world_instance_id: WorldInstanceId
    ) -> Sequence[ScheduledEvent]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.scheduled_events.list_pending(world_instance_id))

    def list_consequences(
        self, world_instance_id: WorldInstanceId
    ) -> Sequence[Consequence]:
        """Внутренний запрос: игровому интерфейсу последствия не показываются."""
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.consequences.list_for_instance(world_instance_id))

    def list_consequences_caused_by(
        self, world_instance_id: WorldInstanceId, event_id: EventId
    ) -> Sequence[Consequence]:
        """Следствия события: база для графа последствий (§25) и аудита (§79)."""
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.consequences.list_caused_by(world_instance_id, event_id))

    def list_consequences_caused_by_consequence(
        self, world_instance_id: WorldInstanceId, consequence_id: ConsequenceId
    ) -> Sequence[Consequence]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(
                uow.consequences.list_caused_by_consequence(world_instance_id, consequence_id)
            )

    # --- запросы -----------------------------------------------------------

    def view_location(
        self,
        world_instance_id: WorldInstanceId,
        *,
        observer_id: CharacterId,
        location_key: LocationKey,
    ) -> LocationView:
        """Публичные факты локации для наблюдателя, который в ней находится.

        Знание и truth в проекцию не попадают по построению
        (см. application/queries/location_view.py).
        """
        return self._location_view.get(
            world_instance_id, location_key, observer_id=observer_id
        )

    def get_instance(self, world_instance_id: WorldInstanceId) -> WorldInstance:
        with self._uow_factory() as uow:
            return uow.world_instances.get(world_instance_id)

    def list_instances(self) -> Sequence[WorldInstance]:
        with self._uow_factory() as uow:
            return uow.world_instances.list_all()

    def get_world_time(self, world_instance_id: WorldInstanceId) -> datetime:
        instance = self.get_instance(world_instance_id)
        return instance.world_time_at(self._clock.now())

    def get_events(self, world_instance_id: WorldInstanceId) -> Sequence[Event]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)  # NOT_FOUND вместо пустого списка
            return list(uow.events.list_for_instance(world_instance_id))

    def get_time_points(
        self, world_instance_id: WorldInstanceId, event_id: EventId
    ) -> Sequence[TimePoint]:
        events = self.get_events(world_instance_id)
        return tuple(
            point
            for event in events
            for point in event.time_points
            if point.event_id == event_id
        )

    def get_character(self, world_instance_id: WorldInstanceId, character_id: CharacterId):
        with self._uow_factory() as uow:
            return uow.characters.get(world_instance_id, character_id)

    def find_active_character_for_player(
        self, world_instance_id: WorldInstanceId, player_id: str
    ) -> Character | None:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return uow.characters.find_by_instance_and_player(world_instance_id, player_id)

    def get_locations(self, world_instance_id: WorldInstanceId):
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.locations.list_for_instance(world_instance_id))

    def get_information(self, world_instance_id: WorldInstanceId, key: str):
        with self._uow_factory() as uow:
            return uow.information.get_by_key(world_instance_id, key)

    def get_knowledge(self, world_instance_id: WorldInstanceId, character_id: CharacterId) -> Sequence[Knowledge]:
        with self._uow_factory() as uow:
            uow.characters.get(world_instance_id, character_id)
            return list(
                uow.knowledge.list_for_subject(
                    world_instance_id, SubjectType.CHARACTER, str(character_id)
                )
            )

    def get_inventory(
        self, world_instance_id: WorldInstanceId, character_id: CharacterId
    ) -> InventoryView:
        return self._inventory_view.get(world_instance_id, character_id)

    def get_npc(self, world_instance_id: WorldInstanceId, npc_id: NpcId) -> Npc:
        with self._uow_factory() as uow:
            return uow.npcs.get(world_instance_id, npc_id)

    def get_npcs(self, world_instance_id: WorldInstanceId) -> Sequence[Npc]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.npcs.list_for_instance(world_instance_id))

    def get_faction(self, world_instance_id: WorldInstanceId, faction_id: FactionId) -> Faction:
        with self._uow_factory() as uow:
            return uow.factions.get(world_instance_id, faction_id)

    def get_factions(self, world_instance_id: WorldInstanceId) -> Sequence[Faction]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.factions.list_for_instance(world_instance_id))

    def view_factions(self, world_instance_id: WorldInstanceId) -> Sequence[FactionView]:
        return self._faction_view.list_for_instance(world_instance_id)

    def get_case(
        self, world_instance_id: WorldInstanceId, case_id: CaseId, *, viewer_id: CharacterId
    ) -> CaseView:
        return self._case_view.get_case(world_instance_id, case_id, viewer_id=viewer_id)

    def list_cases(
        self, world_instance_id: WorldInstanceId, *, viewer_id: CharacterId
    ) -> Sequence[CaseView]:
        return self._case_view.list_cases(world_instance_id, viewer_id=viewer_id)

    def get_case_evidence(
        self, world_instance_id: WorldInstanceId, case_id: CaseId, *, viewer_id: CharacterId
    ) -> Sequence[CaseEvidenceView]:
        return self._case_view.get_case_evidence(
            world_instance_id, case_id, viewer_id=viewer_id
        )

    def get_case_theories(
        self, world_instance_id: WorldInstanceId, case_id: CaseId, *, viewer_id: CharacterId
    ) -> Sequence[CaseTheoryView]:
        return self._case_view.get_case_theories(
            world_instance_id, case_id, viewer_id=viewer_id
        )

    def get_case_notes(
        self, world_instance_id: WorldInstanceId, case_id: CaseId, *, viewer_id: CharacterId
    ) -> Sequence[CaseNoteView]:
        return self._case_view.get_case_notes(world_instance_id, case_id, viewer_id=viewer_id)

    def get_case_suspects(
        self, world_instance_id: WorldInstanceId, case_id: CaseId, *, viewer_id: CharacterId
    ) -> Sequence[CaseSuspectView]:
        return self._case_view.get_case_suspects(
            world_instance_id, case_id, viewer_id=viewer_id
        )

    def get_faction_relations(
        self,
        world_instance_id: WorldInstanceId,
        faction_id: FactionId,
        *,
        only_public: bool = True,
    ) -> Sequence[Relationship]:
        faction_ref = SubjectRef(type=SubjectType.FACTION, id=str(faction_id))
        with self._uow_factory() as uow:
            uow.factions.get(world_instance_id, faction_id)
            relations = uow.relationships.list_of(world_instance_id, faction_ref)
            if only_public:
                return [
                    relation
                    for relation in relations
                    if relation.visibility is RelationshipVisibility.PUBLIC
                ]
            return list(relations)

    def get_npc_definition(self, npc_key: str) -> NpcDefinition:
        """Определение NPC из контента (имя, описание, цели)."""
        return self._catalog.npc_definition(npc_key)

    def get_relationship(
        self,
        world_instance_id: WorldInstanceId,
        *,
        holder: SubjectRef,
        subject: SubjectRef,
        kind: RelationshipKind,
    ) -> Relationship | None:
        """Внутренний запрос: ``None`` означает базовую ступень.

        Наружу (в CLI) отношения не выводятся: игрок видит только поведение и
        последствия, а не внутренние оценки NPC.
        """
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return uow.relationships.find(world_instance_id, holder, subject, kind)

    def list_relationships_of(
        self, world_instance_id: WorldInstanceId, holder: SubjectRef
    ) -> Sequence[Relationship]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.relationships.list_of(world_instance_id, holder))

    def list_relationships_about(
        self, world_instance_id: WorldInstanceId, subject: SubjectRef
    ) -> Sequence[Relationship]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.relationships.list_about(world_instance_id, subject))

    def get_npc_knowledge(
        self, world_instance_id: WorldInstanceId, npc_id: NpcId
    ) -> Sequence[Knowledge]:
        """Знание NPC. Наружу (в CLI) не выводится: это внутренняя память мира."""
        with self._uow_factory() as uow:
            uow.npcs.get(world_instance_id, npc_id)
            return list(
                uow.knowledge.list_for_subject(world_instance_id, SubjectType.NPC, str(npc_id))
            )

    # --- внутреннее --------------------------------------------------------

    def _apply(
        self,
        world_instance_id: WorldInstanceId,
        event_type: EventType,
        *,
        cause: str,
        target: str | None,
        payload_factory: Callable[[WorldInstance], Mapping[str, Any]],
        actor: str = "system",
    ) -> WorldInstance:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            expected_version = instance.state.state_version
            now = self._clock.now()
            event = Event(
                id=self._new_event_id(),
                world_instance_id=world_instance_id,
                type=event_type,
                created_at=now,
                # В коммите 1 применение мгновенное, поэтому executed_at == created_at.
                # Разделение понадобится для отложенных (scheduled) событий.
                executed_at=now,
                actor=actor,
                target=target,
                cause=cause,
                payload=dict(payload_factory(instance)),
                result="success",
            )
            if uow.events.has_event(world_instance_id, event.id):
                raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event.id}")

            instance.apply(event)          # правила domain; при ошибке — откат
            uow.events.append(event)       # идемпотентность и append-only
            uow.world_instances.save(instance, expected_state_version=expected_version)
            uow.commit()
        return instance
