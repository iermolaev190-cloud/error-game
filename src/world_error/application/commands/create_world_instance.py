"""Создание WORLD INSTANCE.

Инстанс, его instance-состояние и событие ``WORLD_INSTANCE_CREATED``
записываются в одной транзакции: мира без записи о его создании быть не может.

При создании мира из контента материализуется instance-состояние:
* ``LocationState`` для каждой локации (UNDISCOVERED);
* ``Information`` для каждого информационного объекта (UNDISCOVERED);
* ``Npc`` для каждого NPC (ACTIVE, в стартовой локации);
* ``Faction`` для каждой faction definition;
* ``Item`` instances из item keys в ``LocationDefinition.items``.

Информация и NPC существуют в мире независимо от того, нашёл их кто-то или нет
(19_MVP §16 design; 05_NPCS §1), поэтому они создаются здесь, а не в момент
первого взаимодействия. Items создаются только там, где на них ссылается
content локации; персонажи стартуют с пустым инвентарём. Материализация — часть создания мира, поэтому
отдельного события не требует: её покрывает ``WORLD_INSTANCE_CREATED``, и
``state_version`` остаётся 0.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable

from world_error.application.ports.chat_bindings import ChatBinding
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.factions.faction import Faction
from world_error.domain.items.item import Item, ItemOwnerType
from world_error.domain.information.information import Information
from world_error.domain.investigations.case import Case, CaseEvidenceLink
from world_error.domain.locations.location import LocationState
from world_error.domain.npcs.npc import Npc
from world_error.domain.shared.kernel import (
    Clock,
    CaseEvidenceLinkId,
    CaseId,
    EventId,
    FactionId,
    ItemId,
    InformationId,
    NpcId,
    WorldInstanceId,
    new_event_id,
    new_case_evidence_link_id,
    new_case_id,
    new_faction_id,
    new_item_id,
    new_information_id,
    new_npc_id,
    new_world_instance_id,
)
from world_error.domain.world.instance import InstanceEnvironment, WorldInstance


@dataclass(frozen=True, slots=True)
class CreateWorldInstanceCommand:
    telegram_chat_id: int
    seed: int
    environment: InstanceEnvironment = InstanceEnvironment.DEV
    actor: str = "system"


class CreateWorldInstanceHandler:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        catalog: ContentCatalog,
        new_instance_id: Callable[[], WorldInstanceId] = new_world_instance_id,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_information_id_factory: Callable[[], InformationId] = new_information_id,
        new_npc_id_factory: Callable[[], NpcId] = new_npc_id,
        new_faction_id_factory: Callable[[], FactionId] = new_faction_id,
        new_item_id_factory: Callable[[], ItemId] = new_item_id,
        new_case_id_factory: Callable[[], CaseId] = new_case_id,
        new_case_evidence_link_id_factory: Callable[[], CaseEvidenceLinkId] = new_case_evidence_link_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._catalog = catalog
        self._new_instance_id = new_instance_id
        self._new_event_id = new_event_id_factory
        self._new_information_id = new_information_id_factory
        self._new_npc_id = new_npc_id_factory
        self._new_faction_id = new_faction_id_factory
        self._new_item_id = new_item_id_factory
        self._new_case_id = new_case_id_factory
        self._new_case_evidence_link_id = new_case_evidence_link_id_factory

    def handle(self, command: CreateWorldInstanceCommand) -> WorldInstance:
        now = self._clock.now()
        instance = WorldInstance.create(
            id=self._new_instance_id(),
            telegram_chat_id=command.telegram_chat_id,
            seed=command.seed,
            content_version=self._catalog.version,
            environment=command.environment,
            now=now,
        )
        event = Event(
            id=self._new_event_id(),
            world_instance_id=instance.id,
            type=EventType.WORLD_INSTANCE_CREATED,
            created_at=now,
            executed_at=now,
            actor=command.actor,
            target=str(instance.id),
            cause="create_world_instance",
            payload={
                "telegram_chat_id": command.telegram_chat_id,
                "seed": command.seed,
                "environment": command.environment.value,
                "content_version": self._catalog.version,
            },
            result="success",
        )
        # Событие создания фиксируется, но state_version созданного инстанса = 0.
        instance.apply(event)

        with self._uow_factory() as uow:
            uow.world_instances.add(instance)
            uow.chat_bindings.add(
                ChatBinding(
                    telegram_chat_id=command.telegram_chat_id,
                    world_instance_id=instance.id,
                    created_at=now,
                )
            )
            for location_definition in self._catalog.locations.values():
                uow.locations.add(
                    LocationState(
                        world_instance_id=instance.id,
                        key=location_definition.key,
                        updated_at=now,
                    )
                )
            for information_definition in self._catalog.information.values():
                uow.information.add(
                    Information(
                        id=self._new_information_id(),
                        world_instance_id=instance.id,
                        key=information_definition.key,
                        location_key=information_definition.location_key,
                        created_at=now,
                    )
                )
            for npc_definition in self._catalog.npcs.values():
                uow.npcs.add(
                    Npc.create(
                        id=self._new_npc_id(),
                        world_instance_id=instance.id,
                        key=npc_definition.key,
                        location_key=npc_definition.initial_location,
                        now=now,
                    )
                )
            for faction_definition in self._catalog.factions.values():
                uow.factions.add(
                    Faction.create(
                        id=self._new_faction_id(),
                        world_instance_id=instance.id,
                        key=faction_definition.key,
                        location_keys=faction_definition.locations,
                        now=now,
                    )
                )
            for location_definition in self._catalog.locations.values():
                spawn_counts = Counter(location_definition.items)
                for item_key, count in spawn_counts.items():
                    item_definition = self._catalog.item_definition(item_key)
                    quantities = (count,) if item_definition.stackable else (1,) * count
                    for quantity in quantities:
                        uow.items.add(
                            Item.create(
                                id=self._new_item_id(),
                                world_instance_id=instance.id,
                                definition=item_definition,
                                owner_type=ItemOwnerType.LOCATION,
                                owner_id=None,
                                location_key=location_definition.key,
                                quantity=quantity,
                                now=now,
                            )
                        )
            for case_definition in self._catalog.cases.values():
                case = Case.open(
                    id=self._new_case_id(),
                    world_instance_id=instance.id,
                    definition=case_definition,
                    now=now,
                )
                uow.cases.add(case)
                for initial_evidence in case_definition.initial_evidence:
                    information = uow.information.get_by_key(
                        instance.id, initial_evidence.information_key
                    )
                    uow.cases.add_evidence_link(
                        CaseEvidenceLink(
                            id=self._new_case_evidence_link_id(),
                            world_instance_id=instance.id,
                            case_id=case.id,
                            information_id=information.id,
                            knowledge_id=None,
                            relevance=initial_evidence.relevance,
                            added_by=None,
                            added_at=now,
                        )
                    )
            uow.events.append(event)
            uow.commit()
        return instance
