"""Публичная проекция локации.

Что видит любой, кто физически находится в локации: сама локация (имя, тип,
описание из контента), её `discovery_state` как факт мира и присутствующие
персонажи (имя и активность).

Чего в проекции нет и не может быть: знания и канонической истины. Это
структурная гарантия, а не соглашение — в `LocationView` и `CharacterPresence`
просто отсутствуют соответствующие поля, и тест сверяет их набор через
``dataclasses.fields``. Канон: EXISTENCE ≠ VISIBILITY ≠ KNOWLEDGE ≠ ACCESS
(11_WORLD_STATE_V1 §29–30).

Запрос требует наблюдателя, который сам находится в этой локации: слепой
просмотр чужих локаций запрещён (``NOT_ALLOWED``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    LocationKey,
    WorldInstanceId,
)


@dataclass(frozen=True, slots=True)
class CharacterPresence:
    """Публичный факт присутствия: кто и в каком состоянии активности."""

    character_id: str
    name: str
    activity: str


@dataclass(frozen=True, slots=True)
class LocationView:
    """Публичные факты локации. Ни знания, ни truth здесь нет по построению."""

    world_instance_id: str
    location_key: str
    name: str
    type: str
    description: str
    discovery_state: str
    characters: tuple[CharacterPresence, ...]


class LocationViewQuery:
    """Читающий запрос: состояние мира не меняется, событий не создаётся."""

    def __init__(self, uow_factory: UnitOfWorkFactory, catalog: ContentCatalog) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog

    def get(
        self,
        world_instance_id: WorldInstanceId,
        location_key: LocationKey,
        *,
        observer_id: CharacterId,
    ) -> LocationView:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            observer = uow.characters.get(instance.id, observer_id)
            observer.ensure_can_act()

            definition = self._catalog.location(location_key)  # NOT_FOUND
            if observer.location_key != location_key:
                raise DomainError(
                    ErrorCode.NOT_ALLOWED,
                    f"observer {observer.id} is in {observer.location_key}, "
                    f"not in {location_key}",
                )

            location_state = uow.locations.get(instance.id, location_key)
            present = uow.characters.list_by_location(instance.id, location_key)

            return LocationView(
                world_instance_id=str(instance.id),
                location_key=str(location_key),
                name=definition.name,
                type=definition.type,
                description=definition.description,
                discovery_state=location_state.discovery_state.value,
                characters=tuple(
                    CharacterPresence(
                        character_id=str(character.id),
                        name=character.name,
                        activity=character.activity.value,
                    )
                    for character in present
                ),
            )
