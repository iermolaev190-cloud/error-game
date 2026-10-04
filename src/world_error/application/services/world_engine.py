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
from typing import Any, Callable, Mapping, Sequence

from world_error.application.action_result import ActionResult
from world_error.application.commands.apply_significant_action import (
    ApplySignificantActionCommand,
    ApplySignificantActionHandler,
)
from world_error.application.commands.change_relationship import (
    ChangeRelationshipCommand,
    ChangeRelationshipHandler,
)
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
from world_error.application.commands.share_knowledge import (
    ShareKnowledgeCommand,
    ShareKnowledgeHandler,
)
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.application.queries.location_view import LocationView, LocationViewQuery
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
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
    SubjectRef,
)
from world_error.domain.relationships.rules import SignificantAction
from world_error.domain.shared.kernel import (
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    NpcId,
    SystemClock,
    WorldInstanceId,
    new_event_id,
)
from world_error.domain.world.instance import InstanceEnvironment, InstanceLifecycle, WorldInstance

DEFAULT_SEED_BITS = 63


class WorldEngine:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        catalog: ContentCatalog,
        clock: Clock | None = None,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog
        self._clock = clock or SystemClock()
        self._new_event_id = new_event_id_factory
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
        self._move_character = MoveCharacterHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            catalog=catalog,
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
        self._change_relationship = ChangeRelationshipHandler(
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
        """
        return self._apply(
            world_instance_id,
            EventType.WORLD_TICK_ADVANCED,
            cause=cause,
            target=str(world_instance_id),
            payload_factory=lambda instance: {
                "from_tick": instance.state.world_tick,
                "to_tick": instance.state.world_tick + 1,
            },
        )

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
        return self._apply(
            world_instance_id,
            EventType.WORLD_INSTANCE_STATUS_CHANGED,
            cause=cause,
            target=str(world_instance_id),
            payload_factory=lambda instance: {"from": instance.lifecycle.value, "to": target.value},
        )

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

    def move_character(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        to_location_key: LocationKey,
        cause: str = "move",
    ) -> ActionResult:
        return self._move_character.handle(
            MoveCharacterCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                to_location_key=to_location_key,
                cause=cause,
            )
        )

    def inspect_information(
        self,
        world_instance_id: WorldInstanceId,
        *,
        character_id: CharacterId,
        target_key: str,
        cause: str = "inspect",
    ) -> ActionResult:
        return self._inspect_information.handle(
            InspectInformationCommand(
                world_instance_id=world_instance_id,
                character_id=character_id,
                target_key=target_key,
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

    # --- отношения (коммит 5) ----------------------------------------------

    def change_relationship(
        self,
        world_instance_id: WorldInstanceId,
        *,
        holder: SubjectRef,
        subject: SubjectRef,
        kind: RelationshipKind,
        direction: RelationshipDirection,
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
                reason=reason,
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

    def get_events(self, world_instance_id: WorldInstanceId) -> Sequence[Event]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)  # NOT_FOUND вместо пустого списка
            return list(uow.events.list_for_instance(world_instance_id))

    def get_character(self, world_instance_id: WorldInstanceId, character_id: CharacterId):
        with self._uow_factory() as uow:
            return uow.characters.get(world_instance_id, character_id)

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

    def get_npc(self, world_instance_id: WorldInstanceId, npc_id: NpcId) -> Npc:
        with self._uow_factory() as uow:
            return uow.npcs.get(world_instance_id, npc_id)

    def get_npcs(self, world_instance_id: WorldInstanceId) -> Sequence[Npc]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)
            return list(uow.npcs.list_for_instance(world_instance_id))

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
