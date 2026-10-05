"""Порты доступа к состоянию мира и журналу событий.

Все операции выполняются в контексте одного ``world_instance_id``
(MASTER_SPEC §7): ``handle_intent(world_instance_id, actor_id, intent)``.
Данные разных WORLD INSTANCE не смешиваются.
"""

from __future__ import annotations

from typing import Callable, Protocol, Sequence

from world_error.domain.characters.character import Character
from world_error.domain.investigations.case import (
    Case,
    CaseContradictionLink,
    CaseEvidenceLink,
    CaseNote,
    CaseQuestion,
    CaseSuspectLink,
    CaseTheory,
    CaseTheoryEvidenceLink,
)
from world_error.domain.consequences.consequence import Consequence
from world_error.domain.events.log import EventLog
from world_error.domain.factions.faction import Faction
from world_error.domain.information.information import Information
from world_error.domain.items.item import Item, ItemOwnerType
from world_error.domain.knowledge.knowledge import Knowledge, SubjectType
from world_error.domain.locations.location import LocationState
from world_error.domain.legacy.legacy_document import LegacyDocument
from world_error.domain.npcs.npc import Npc
from world_error.domain.relationships.relationship import (
    Relationship,
    RelationshipKind,
    SubjectRef,
)
from world_error.domain.shared.kernel import (
    CharacterId,
    CaseEvidenceLinkId,
    CaseId,
    CaseTheoryId,
    ConsequenceId,
    EventId,
    FactionId,
    InformationId,
    ItemId,
    LocationKey,
    LegacyDocumentId,
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

    def get(self, world_instance_id: WorldInstanceId, information_id: InformationId) -> Information: ...

    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Information: ...

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> Sequence[Information]: ...

    def save(self, information: Information) -> None: ...


class KnowledgeRepository(Protocol):
    def add(self, knowledge: Knowledge) -> None: ...

    def get(self, world_instance_id: WorldInstanceId, knowledge_id: KnowledgeId) -> Knowledge: ...

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


class FactionRepository(Protocol):
    def add(self, faction: Faction) -> None: ...

    def get(self, world_instance_id: WorldInstanceId, faction_id: FactionId) -> Faction: ...

    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Faction: ...

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> Sequence[Faction]: ...

    def save(self, faction: Faction) -> None: ...


class ItemRepository(Protocol):
    def add(self, item: Item) -> None: ...

    def get(self, world_instance_id: WorldInstanceId, item_id: ItemId) -> Item: ...

    def list_by_owner(
        self,
        world_instance_id: WorldInstanceId,
        owner_type: ItemOwnerType,
        owner_id: str | None,
    ) -> Sequence[Item]: ...

    def list_at_location(
        self, world_instance_id: WorldInstanceId, location_key: LocationKey
    ) -> Sequence[Item]: ...

    def find_stack(
        self,
        world_instance_id: WorldInstanceId,
        key: str,
        owner_type: ItemOwnerType,
        owner_id: str | None,
        location_key: LocationKey | None,
    ) -> Item | None: ...

    def save(self, item: Item) -> None: ...

    def delete(self, item: Item) -> None: ...


class CaseRepository(Protocol):
    def add(self, case: Case) -> None: ...
    def get(self, world_instance_id: WorldInstanceId, case_id: CaseId) -> Case: ...
    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Case: ...
    def list_for_instance(self, world_instance_id: WorldInstanceId) -> Sequence[Case]: ...
    def save(self, case: Case) -> None: ...
    def add_evidence_link(self, link: CaseEvidenceLink) -> None: ...
    def find_evidence_link(
        self, world_instance_id: WorldInstanceId, case_id: CaseId, information_id: InformationId
    ) -> CaseEvidenceLink | None: ...
    def get_evidence_link(
        self, world_instance_id: WorldInstanceId, link_id: CaseEvidenceLinkId
    ) -> CaseEvidenceLink: ...
    def list_evidence(
        self, world_instance_id: WorldInstanceId, case_id: CaseId
    ) -> Sequence[CaseEvidenceLink]: ...
    def save_evidence_link(self, link: CaseEvidenceLink) -> None: ...
    def add_theory(self, theory: CaseTheory) -> None: ...
    def get_theory(self, world_instance_id: WorldInstanceId, theory_id: CaseTheoryId) -> CaseTheory: ...
    def list_theories(
        self, world_instance_id: WorldInstanceId, case_id: CaseId
    ) -> Sequence[CaseTheory]: ...
    def save_theory(self, theory: CaseTheory) -> None: ...
    def add_theory_evidence_link(self, link: CaseTheoryEvidenceLink) -> None: ...
    def list_theory_evidence(
        self, world_instance_id: WorldInstanceId, theory_id: CaseTheoryId
    ) -> Sequence[CaseTheoryEvidenceLink]: ...
    def add_contradiction(self, link: CaseContradictionLink) -> None: ...
    def list_contradictions(
        self, world_instance_id: WorldInstanceId, case_id: CaseId
    ) -> Sequence[CaseContradictionLink]: ...
    def find_suspect(
        self, world_instance_id: WorldInstanceId, case_id: CaseId, subject_type: SubjectType,
        subject_id: str
    ) -> CaseSuspectLink | None: ...
    def add_suspect(self, link: CaseSuspectLink) -> None: ...
    def save_suspect(self, link: CaseSuspectLink) -> None: ...
    def list_suspects(
        self, world_instance_id: WorldInstanceId, case_id: CaseId
    ) -> Sequence[CaseSuspectLink]: ...
    def add_note(self, note: CaseNote) -> None: ...
    def list_notes(self, world_instance_id: WorldInstanceId, case_id: CaseId) -> Sequence[CaseNote]: ...
    def add_question(self, question: CaseQuestion) -> None: ...
    def list_questions(
        self, world_instance_id: WorldInstanceId, case_id: CaseId
    ) -> Sequence[CaseQuestion]: ...


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


class LegacyDocumentRepository(Protocol):
    def add(self, document: LegacyDocument) -> None: ...

    def get(self, world_instance_id: WorldInstanceId, document_id: LegacyDocumentId) -> LegacyDocument: ...

    def list_at_location(
        self, world_instance_id: WorldInstanceId, location_key: LocationKey
    ) -> Sequence[LegacyDocument]: ...


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
    legacy_documents: LegacyDocumentRepository

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
