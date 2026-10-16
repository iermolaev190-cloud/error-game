"""Передача знания между персонажами (SHARE).

Правила среза 3a:

* делится персонаж A, получает персонаж B, оба — в одной локации одного
  WORLD INSTANCE (иначе ``NOT_ALLOWED``);
* получатель должен быть ``ALIVE``; ``activity`` приём не блокирует — INACTIVE
  значит «игрок оффлайн», а не наказание персонажа;
* делиться можно только тем, что A действительно знает, иначе ``INVALID_ACTION``;
* в знание B попадает **claim** из записи знания A, а не truth: обработчик не
  читает каталог контента вообще, поэтому канонический факт структурно
  недостижим в этом пути;
* если B уже знает эту информацию (сам наблюдал или получил ранее) — успешный
  no-op без нового события: ``FACT`` не понижается до ``CLAIM``.

Одно действие — одно событие ``KNOWLEDGE_SHARED``. ``Information`` и
``LocationState`` этим событием не меняются: мир не узнаёт ничего нового о
себе, знание меняется только у получателя.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.characters.character import CharacterLifecycle
from world_error.domain.events.event import Event, EventType
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
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


@dataclass(frozen=True, slots=True)
class ShareKnowledgeCommand:
    world_instance_id: WorldInstanceId
    sharer_id: CharacterId
    receiver_id: CharacterId
    information_key: str
    cause: str = "share"


class ShareKnowledgeHandler:
    ACTION = "SHARE"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_knowledge_id_factory: Callable[[], KnowledgeId] = new_knowledge_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._new_event_id = new_event_id_factory
        self._new_knowledge_id = new_knowledge_id_factory

    def handle(self, command: ShareKnowledgeCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version

                sharer = uow.characters.get(instance.id, command.sharer_id)
                sharer.ensure_can_act()

                # Персонаж другого INSTANCE здесь не виден: репозиторий
                # ограничен своим миром → NOT_FOUND, данные не смешиваются.
                receiver = uow.characters.get(instance.id, command.receiver_id)
                if receiver.lifecycle is not CharacterLifecycle.ALIVE:
                    raise DomainError(
                        ErrorCode.NOT_ALLOWED,
                        f"receiver {receiver.id} is not alive",
                    )
                if sharer.location_key != receiver.location_key:
                    raise DomainError(
                        ErrorCode.NOT_ALLOWED,
                        f"characters are in different locations: "
                        f"{sharer.location_key} != {receiver.location_key}",
                    )

                information = uow.information.get_by_key(instance.id, command.information_key)

                already_known = uow.knowledge.find(
                    instance.id, SubjectType.CHARACTER, str(receiver.id), information.id
                )
                if already_known is not None:
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "already_known": True,
                            "information_key": information.key,
                            "sharer_character_id": str(sharer.id),
                            "receiver_character_id": str(receiver.id),
                            "claim": already_known.claim,
                            "claim_type": already_known.claim_type.value,
                            "source": already_known.source.value,
                            "source_ref": already_known.source_ref or "",
                            "confidence": already_known.confidence.value,
                            "world_tick": instance.state.world_tick,
                            "state_version": instance.state.state_version,
                        },
                    )

                sharer_knowledge = uow.knowledge.find(
                    instance.id, SubjectType.CHARACTER, str(sharer.id), information.id
                )
                if sharer_knowledge is None:
                    raise DomainError(
                        ErrorCode.INVALID_ACTION,
                        f"character {sharer.id} has no knowledge of {information.key}",
                    )

                now = self._clock.now()
                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.KNOWLEDGE_SHARED,
                    created_at=now,
                    executed_at=now,
                    actor=str(sharer.id),
                    target=str(receiver.id),
                    cause=command.cause,
                    payload={
                        "information_key": information.key,
                        "sharer_character_id": str(sharer.id),
                        "receiver_character_id": str(receiver.id),
                        "claim_type": ClaimType.CLAIM.value,
                        "source": KnowledgeSource.CHARACTER.value,
                        "source_ref": str(sharer.id),
                    },
                    result="success",
                )
                instance.register_applied_event(event)
                knowledge = Knowledge.from_share(
                    id=self._new_knowledge_id(),
                    sharer=sharer,
                    sharer_knowledge=sharer_knowledge,
                    receiver=receiver,
                    now=now,
                )

                uow.knowledge.add(knowledge)
                uow.world_instances.save(instance, expected_state_version=expected_version)
                uow.events.append(event)
                uow.commit()

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "already_known": False,
                    "information_key": information.key,
                    "sharer_character_id": str(sharer.id),
                    "receiver_character_id": str(receiver.id),
                    "claim": knowledge.claim,
                    "claim_type": knowledge.claim_type.value,
                    "source": knowledge.source.value,
                    "source_ref": knowledge.source_ref or "",
                    "confidence": knowledge.confidence.value,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
