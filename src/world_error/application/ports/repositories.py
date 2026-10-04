"""Порты доступа к состоянию мира и журналу событий.

Все операции выполняются в контексте одного ``world_instance_id``
(MASTER_SPEC §7): ``handle_intent(world_instance_id, actor_id, intent)``.
Данные разных WORLD INSTANCE не смешиваются.
"""

from __future__ import annotations

from typing import Callable, Protocol, Sequence

from world_error.domain.characters.character import Character
from world_error.domain.events.log import EventLog
from world_error.domain.information.information import Information
from world_error.domain.knowledge.knowledge import Knowledge, SubjectType
from world_error.domain.locations.location import LocationState
from world_error.domain.shared.kernel import (
    CharacterId,
    InformationId,
    LocationKey,
    WorldInstanceId,
)
from world_error.domain.world.instance import WorldInstance


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

    def __enter__(self) -> "UnitOfWork": ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
