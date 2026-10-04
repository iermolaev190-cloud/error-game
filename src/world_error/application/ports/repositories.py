"""Порты доступа к состоянию мира и журналу событий.

Все операции выполняются в контексте одного ``world_instance_id``
(MASTER_SPEC §7): ``handle_intent(world_instance_id, actor_id, intent)``.
Данные разных WORLD INSTANCE не смешиваются.
"""

from __future__ import annotations

from typing import Callable, Protocol, Sequence

from world_error.domain.characters.character import Character
from world_error.domain.consequences.consequence import Consequence
from world_error.domain.events.log import EventLog
from world_error.domain.information.information import Information
from world_error.domain.knowledge.knowledge import Knowledge, SubjectType
from world_error.domain.locations.location import LocationState
from world_error.domain.npcs.npc import Npc
from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipKind,
    SubjectRef,
)
from world_error.domain.shared.kernel import (
    CharacterId,
    ConsequenceId,
    EventId,
    InformationId,
    LocationKey,
    NpcId,
    ScheduledEventId,
    WorldInstanceId,
)
from world_error.domain.world.instance import WorldInstance
from world_error.domain.time.scheduled_event import ScheduledEvent


class WorldInstanceRepository(Protocol):
    def add(self, instance: WorldInstance) -> None: ...

    def get(self, world_instance_id: WorldInstanceId) -> WorldInstance:
        """Вернуть инстанс или поднять ``DomainError(NOT_FOUND)``."""
        ...

    def save(self, instance: WorldInstance, *, expected_state_version: int) -> None:
        """Сохранить состояние с проверкой версии (optimistic CAS).

        ``expected_state_version`` — версия, прочитанная в начале транзакции.
        Если в БД уже другая версия, значит параллельный запрос успел первым:
        поднимается ``DomainError(CONFLICT)``, транзакция откатывается, и
        потерянных обновлений не возникает (11_WORLD_STATE_V1 §50).
        """
        ...


class CharacterRepository(Protocol):
    def add(self, character: Character) -> None: ...

    def get(self, world_instance_id: WorldInstanceId, character_id: CharacterId) -> Character:
        """Вернуть персонажа своего инстанса или поднять ``DomainError(NOT_FOUND)``."""
        ...

    def find_alive_by_player(
        self, world_instance_id: WorldInstanceId, player_id: str
    ) -> Character | None:
        """Живой персонаж игрока в этом мире (один аккаунт — один персонаж)."""
        ...

    def list_by_location(
        self, world_instance_id: WorldInstanceId, location_key: LocationKey
    ) -> Sequence[Character]:
        """Персонажи указанного INSTANCE, физически находящиеся в локации.

        Данные разных миров не смешиваются: запрос всегда ограничен своим
        ``world_instance_id``.
        """
        ...

    def save(self, character: Character) -> None: ...


class LocationStateRepository(Protocol):
    def add(self, state: LocationState) -> None: ...

    def get(self, world_instance_id: WorldInstanceId, key: LocationKey) -> LocationState: ...

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> Sequence[LocationState]: ...

    def save(self, state: LocationState) -> None: ...


class InformationRepository(Protocol):
    def add(self, information: Information) -> None: ...

    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Information: ...

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> Sequence[Information]: ...

    def save(self, information: Information) -> None: ...


class KnowledgeRepository(Protocol):
    def add(self, knowledge: Knowledge) -> None: ...

    def find(
        self,
        world_instance_id: WorldInstanceId,
        subject_type: SubjectType,
        subject_id: str,
        information_id: InformationId,
    ) -> Knowledge | None: ...

    def list_for_subject(
        self,
        world_instance_id: WorldInstanceId,
        subject_type: SubjectType,
        subject_id: str,
    ) -> Sequence[Knowledge]: ...


class NpcRepository(Protocol):
    def add(self, npc: Npc) -> None: ...

    def get(self, world_instance_id: WorldInstanceId, npc_id: NpcId) -> Npc:
        """Вернуть NPC своего мира или поднять ``DomainError(NOT_FOUND)``."""
        ...

    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Npc: ...

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> Sequence[Npc]: ...

    def list_in_location(
        self, world_instance_id: WorldInstanceId, location_key: LocationKey
    ) -> Sequence[Npc]:
        """NPC, чья последняя известная локация совпадает.

        Фильтр по статусу (только ACTIVE) делает вызывающий: ``MISSING`` NPC
        остаётся здесь лишь «последним известным местом».
        """
        ...

    def save(self, npc: Npc) -> None: ...


class RelationshipRepository(Protocol):
    """Отношения асимметричны: holder → subject и subject → holder — разные записи."""

    def add(self, relationship: Relationship) -> None: ...

    def find(
        self,
        world_instance_id: WorldInstanceId,
        holder: SubjectRef,
        subject: SubjectRef,
        kind: RelationshipKind,
    ) -> Relationship | None:
        """Запись или ``None``: отсутствие записи означает базовую ступень."""
        ...

    def list_of(
        self, world_instance_id: WorldInstanceId, holder: SubjectRef
    ) -> Sequence[Relationship]: ...

    def list_about(
        self, world_instance_id: WorldInstanceId, subject: SubjectRef
    ) -> Sequence[Relationship]: ...

    def save(self, relationship: Relationship) -> None: ...


class ConsequenceRepository(Protocol):
    """Последствия и их причины. Причина — часть агрегата, а не ссылка «где-то»."""

    def add(self, consequence: Consequence) -> None: ...

    def get(
        self, world_instance_id: WorldInstanceId, consequence_id: ConsequenceId
    ) -> Consequence: ...

    def find_by_rule(
        self,
        world_instance_id: WorldInstanceId,
        rule_key: str,
        source_event_id: EventId,
    ) -> Consequence | None:
        """Сработало ли правило на это событие: материализация идемпотентна."""
        ...

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> Sequence[Consequence]: ...

    def list_pending(self, world_instance_id: WorldInstanceId) -> Sequence[Consequence]: ...

    def list_caused_by(
        self, world_instance_id: WorldInstanceId, event_id: EventId
    ) -> Sequence[Consequence]:
        """Ветвление (§25): у одного события может быть несколько последствий."""
        ...

    def list_caused_by_consequence(
        self, world_instance_id: WorldInstanceId, consequence_id: ConsequenceId
    ) -> Sequence[Consequence]: ...

    def save(self, consequence: Consequence) -> None: ...


class ScheduledEventRepository(Protocol):
    def add(self, item: ScheduledEvent) -> None: ...

    def get(
        self, world_instance_id: WorldInstanceId, scheduled_event_id: ScheduledEventId
    ) -> ScheduledEvent: ...

    def find_by_idempotency_key(
        self, world_instance_id: WorldInstanceId, idempotency_key: str
    ) -> ScheduledEvent | None: ...

    def list_pending(self, world_instance_id: WorldInstanceId) -> Sequence[ScheduledEvent]: ...

    def save(self, item: ScheduledEvent) -> None: ...


class UnitOfWork(Protocol):
    """Одна транзакция на один игровой запрос.

    Состояние мира и событие фиксируются вместе: либо всё, либо ничего
    (MASTER_SPEC §14, 20_TECH_ARCHITECTURE_V1 §12).
    """

    world_instances: WorldInstanceRepository
    events: EventLog
    characters: CharacterRepository
    locations: LocationStateRepository
    information: InformationRepository
    knowledge: KnowledgeRepository
    npcs: NpcRepository
    relationships: RelationshipRepository
    consequences: ConsequenceRepository
    scheduled_events: ScheduledEventRepository

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
