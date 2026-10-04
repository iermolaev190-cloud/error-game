"""Исследование информационного объекта: мир получает факт обнаружения, персонаж — знание."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._action_cost import consume_action_cost
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
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    KnowledgeId,
    WorldInstanceId,
    new_event_id,
    new_knowledge_id,
)
from world_error.domain.time.action_cost import CostTicks


@dataclass(frozen=True, slots=True)
class InspectInformationCommand:
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    target_key: str
    cost_ticks: CostTicks | int | None = None
    cause: str = "inspect"


class InspectInformationHandler:
    """INSPECT: одно событие меняет и мир, и знание (11_WORLD_STATE_V1 §62).

    * мир: ``information.discovery_state = DISCOVERED`` и первый нашедший;
    * персонаж: новая запись ``Knowledge``.

    Повторный INSPECT того же объекта тем же персонажем — успешный no-op без
    события: изменения состояния не произошло. ``ALREADY_PROCESSED`` здесь не
    используется — этот код про повторную обработку одного и того же события.
    Знание берётся из ``definition.content``; ``definition.truth`` в знание не
    попадает.
    """

    ACTION = "INSPECT"

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

    def handle(self, command: InspectInformationCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                character = uow.characters.get(instance.id, command.character_id)
                character.ensure_can_act()

                information = uow.information.get_by_key(instance.id, command.target_key)
                if information.location_key != character.location_key:
                    raise DomainError(
                        ErrorCode.NOT_ALLOWED,
                        f"information {information.key} is in {information.location_key}, "
                        f"character is in {character.location_key}",
                    )

                known = uow.knowledge.find(
                    instance.id, SubjectType.CHARACTER, str(character.id), information.id
                )
                if known is not None:
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "already_known": True,
                            "information_key": information.key,
                            "claim": known.claim,
                            "claim_type": known.claim_type.value,
                            "confidence": known.confidence.value,
                            "document_date": (
                                None if known.document_date is None else known.document_date.isoformat()
                            ),
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
                    actor=str(character.id),
                    target=information.key,
                    cause=command.cause,
                    payload={
                        "information_key": information.key,
                        "location_key": str(information.location_key),
                        "claim_type": ClaimType.FACT.value,
                        "source": KnowledgeSource.OBSERVATION.value,
                        "confidence": KnowledgeConfidence.LIKELY.value,
                    },
                    result="success",
                )
                instance.register_applied_event(event)
                information.apply(event)
                knowledge = Knowledge.from_discovery(
                    id=self._new_knowledge_id(),
                    character=character,
                    information=information,
                    definition=definition,
                    now=now,
                )
                cost_event = consume_action_cost(
                    instance,
                    action=self.ACTION,
                    action_event=event,
                    cost=command.cost_ticks,
                    now=now,
                    new_event_id_factory=self._new_event_id,
                )

                uow.information.save(information)
                uow.knowledge.add(knowledge)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                if cost_event is not None:
                    uow.events.append(cost_event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,) + (() if cost_event is None else (cost_event.id,)),
                payload={
                    "already_known": False,
                    "information_key": information.key,
                    "claim": knowledge.claim,
                    "claim_type": knowledge.claim_type.value,
                    "source": knowledge.source.value,
                    "confidence": knowledge.confidence.value,
                    "document_date": (
                        None
                        if knowledge.document_date is None
                        else knowledge.document_date.isoformat()
                    ),
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                    "cost_ticks": None if command.cost_ticks is None else int(command.cost_ticks),
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
