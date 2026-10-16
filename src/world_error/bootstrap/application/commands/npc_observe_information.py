"""NPC сам находит информационный объект — событие INFORMATION_DISCOVERED.

Тип события описывает, что произошло («информация обнаружена»), а кто это
сделал — в ``actor``. Поэтому отдельного ``NPC_ACTED`` нет: NPC действует в
мире тем же событием, что и персонаж (05_NPCS §19).

Мир при этом меняется по-настоящему: ``information.discovery_state`` становится
DISCOVERED, а первый нашедший не перезаписывается, если объект уже находили.
NPC получает собственную запись знания; если он уже знал — знание не дублируется.
Если менять нечего (объект уже найден и NPC уже знает) — успешный no-op без события.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.shared.kernel import (
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    KnowledgeId,
    NpcId,
    WorldInstanceId,
    new_event_id,
    new_knowledge_id,
)


@dataclass(frozen=True, slots=True)
class NpcObserveInformationCommand:
    world_instance_id: WorldInstanceId
    npc_id: NpcId
    information_key: str
    cause: str = "npc_observe"


class NpcObserveInformationHandler:
    ACTION = "NPC_OBSERVE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        catalog: ContentCatalog,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_knowledge_id_factory: Callable[[], KnowledgeId] = new_knowledge_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._catalog = catalog
        self._new_event_id = new_event_id_factory
        self._new_knowledge_id = new_knowledge_id_factory

    def handle(self, command: NpcObserveInformationCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                npc = uow.npcs.get(instance.id, command.npc_id)
                npc.ensure_can_act()

                information = uow.information.get_by_key(instance.id, command.information_key)
                if information.location_key != npc.location_key:
                    raise DomainError(
                        ErrorCode.NOT_ALLOWED,
                        f"information {information.key} is in {information.location_key}, "
                        f"npc is in {npc.location_key}",
                    )

                known = uow.knowledge.find(
                    instance.id, SubjectType.NPC, str(npc.id), information.id
                )
                already_discovered = information.discovery_state.value == "DISCOVERED"
                if known is not None and already_discovered:
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "already_known": True,
                            "information_key": information.key,
                            "npc_id": str(npc.id),
                            "claim": known.claim,
                            "claim_type": known.claim_type.value,
                            "source": known.source.value,
                            "confidence": known.confidence.value,
                            "discovery_state": information.discovery_state.value,
                            "discovered_by": information.discovered_by or "",
                            "world_tick": instance.state.world_tick,
                            "state_version": instance.state.state_version,
                        },
                    )

                definition = self._catalog.information_definition(information.key)
                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.INFORMATION_DISCOVERED,
                    created_at=now,
                    executed_at=now,
                    actor=str(npc.id),
                    target=information.key,
                    cause=command.cause,
                    payload={
                        "information_key": information.key,
                        "location_key": str(information.location_key),
                        "claim_type": ClaimType.OBSERVATION.value,
                        "source": KnowledgeSource.OBSERVATION.value,
                        "confidence": KnowledgeConfidence.LIKELY.value,
                    },
                    result="success",
                )
                instance.register_applied_event(event)
                # Первый нашедший не перезаписывается: apply меняет состояние
                # только если объект ещё UNDISCOVERED.
                information.apply(event)

                knowledge: Knowledge | None = None
                if known is None:
                    knowledge = Knowledge.from_observation(
                        id=self._new_knowledge_id(),
                        world_instance_id=instance.id,
                        subject_type=SubjectType.NPC,
                        subject_id=str(npc.id),
                        information=information,
                        definition=definition,
                        now=now,
                    )
                    uow.knowledge.add(knowledge)

                uow.information.save(information)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()

            record = knowledge if knowledge is not None else known
            assert record is not None
            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "already_known": knowledge is None,
                    "information_key": information.key,
                    "npc_id": str(npc.id),
                    "claim": record.claim,
                    "claim_type": record.claim_type.value,
                    "source": record.source.value,
                    "confidence": record.confidence.value,
                    "discovery_state": information.discovery_state.value,
                    "discovered_by": information.discovered_by or "",
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
