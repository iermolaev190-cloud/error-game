"""Публичная проекция локации.

Что видит любой, кто физически находится в локации: сама локация (имя, тип,
описание из контента), её `discovery_state` как факт мира, присутствующие
персонажи (имя и активность), NPC (имя и статус) и публичные предметы (имя/key).
Скрытые предметы и ownership в проекцию не попадают.

Чего в проекции нет и не может быть: знания, целей NPC и канонической истины.
Это структурная гарантия, а не соглашение — в `LocationView`, `CharacterPresence`
и `NpcPresence` просто отсутствуют соответствующие поля, и тест сверяет их набор
через ``dataclasses.fields``. Канон: EXISTENCE ≠ VISIBILITY ≠ KNOWLEDGE ≠ ACCESS
(11_WORLD_STATE_V1 §29–30), NPC — субъекты мира, а не интерфейс (05_NPCS §35).

Исчезнувший NPC (``MISSING``) не показывается нигде: его местонахождение
неизвестно (05_NPCS §22), поэтому в проекции остаются только ``ACTIVE``.

Запрос требует наблюдателя, который сам находится в этой локации: слепой
просмотр чужих локаций запрещён (``NOT_ALLOWED``). Запрос ничего не меняет.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.items.item import ItemVisibility
from world_error.domain.npcs.npc import NpcStatus
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    LocationKey,
    WorldInstanceId,
)


@dataclass(frozen=True, slots=True)
class CharacterPresence:
    """Публичный факт присутствия персонажа: кто и в каком состоянии активности."""

    character_id: str
    name: str
    activity: str


@dataclass(frozen=True, slots=True)
class NpcPresence:
    """Публичный факт присутствия NPC: только имя и статус.

    Ни знания, ни целей, ни памяти здесь нет и быть не может.
    """

    npc_id: str
    name: str
    status: str


@dataclass(frozen=True, slots=True)
class ItemPresence:
    """Public item presence only: no owner or hidden definition details."""

    key: str
    name: str


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
    npcs: tuple[NpcPresence, ...]
    items: tuple[ItemPresence, ...]
    connections: tuple[str, ...]


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
            players_here = tuple(
                CharacterPresence(
                    character_id=str(character.id),
                    name=character.name,
                    activity=character.activity.value,
                )
                for character in present
            )
            npcs_here = tuple(
                NpcPresence(
                    npc_id=str(npc.id),
                    name=self._catalog.npc_definition(npc.key).name,
                    status=npc.status.value,
                )
                for npc in uow.npcs.list_in_location(instance.id, location_key)
                if npc.status is NpcStatus.ACTIVE
            )
            items_here = tuple(
                ItemPresence(key=item.key, name=self._catalog.item_definition(item.key).name)
                for item in uow.items.list_at_location(instance.id, location_key)
                if self._catalog.item_definition(item.key).visibility is ItemVisibility.PUBLIC
            )

            return LocationView(
                world_instance_id=str(instance.id),
                location_key=str(location_key),
                name=definition.name,
                type=definition.type,
                description=definition.description,
                discovery_state=location_state.discovery_state.value,
                characters=players_here,
                npcs=npcs_here,
                items=items_here,
                connections=tuple(sorted(str(key) for key in definition.connections)),
            )
