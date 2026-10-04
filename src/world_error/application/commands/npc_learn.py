"""NPC узнаёт информацию (вторые руки, документ, слух) — событие NPC_LEARNED.

Граница знания (05_NPCS §26): NPC не знает того, чего ему не передавали. Этот
обработчик — единственный путь «передачи»; ничего не копируется ни из знания
игроков, ни из канонической истины.

``claim`` по умолчанию берётся из ``InformationDefinition.content``. Явно
переданный ``claim`` разрешён: NPC может ошибаться, верить слуху или лгать
себе (05_NPCS §3–§4), и его версия может не совпадать с truth. Truth не
читается вообще — обработчик к нему не обращается.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._subjects import subject_ref_from_id
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
from world_error.domain.relationships.relationship import RelationshipKind, SubjectRef
from world_error.domain.relationships.rules import is_source_distrusted
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
class NpcLearnCommand:
    world_instance_id: WorldInstanceId
    npc_id: NpcId
    information_key: str
    claim_type: ClaimType = ClaimType.FACT
    source: KnowledgeSource = KnowledgeSource.OBSERVATION
    confidence: KnowledgeConfidence = KnowledgeConfidence.LIKELY
    claim: str | None = None
    source_ref: str | None = None
    cause: str = "npc_learn"


class NpcLearnHandler:
    ACTION = "NPC_LEARN"

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

    def handle(self, command: NpcLearnCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                npc = uow.npcs.get(instance.id, command.npc_id)
                npc.ensure_can_act()

                information = uow.information.get_by_key(instance.id, command.information_key)

                already_known = uow.knowledge.find(
                    instance.id, SubjectType.NPC, str(npc.id), information.id
                )
                if already_known is not None:
                    return ActionResult.success(
                        self.ACTION,
                        payload={
                            "already_known": True,
                            "npc_id": str(npc.id),
                            "information_key": information.key,
                            "claim": already_known.claim,
                            "claim_type": already_known.claim_type.value,
                            "source": already_known.source.value,
                            "confidence": already_known.confidence.value,
                        },
                    )

                # Гейт отношений: NPC не принимает знание от того, кому не доверяет
                # (TRUST=HOSTILE или SUSPICION=HIGH). База NEUTRAL/NONE пропускает,
                # поэтому обычные вызовы без source_ref работают как раньше.
                source_subject = (
                    subject_ref_from_id(command.source_ref) if command.source_ref else None
                )
                if source_subject is not None:
                    holder = SubjectRef(type=SubjectType.NPC, id=str(npc.id))
                    trust = uow.relationships.find(
                        instance.id, holder, source_subject, RelationshipKind.TRUST
                    )
                    suspicion = uow.relationships.find(
                        instance.id, holder, source_subject, RelationshipKind.SUSPICION
                    )
                    if is_source_distrusted(
                        trust_level=trust.level if trust is not None else None,
                        suspicion_level=suspicion.level if suspicion is not None else None,
                    ):
                        raise DomainError(
                            ErrorCode.NOT_ALLOWED,
                            f"npc {npc.id} does not trust source {command.source_ref}",
                        )

                definition = self._catalog.information_definition(information.key)
                claim = command.claim if command.claim is not None else definition.content
                now = self._clock.now()

                event = Event(
                    id=self._new_event_id(),
                    world_instance_id=instance.id,
                    type=EventType.NPC_LEARNED,
                    created_at=now,
                    executed_at=now,
                    actor=str(npc.id),
                    target=information.key,
                    cause=command.cause,
                    payload={
                        "npc_key": npc.key,
                        "information_key": information.key,
                        "claim_type": command.claim_type.value,
                        "source": command.source.value,
                        "source_ref": command.source_ref,
                        "confidence": command.confidence.value,
                    },
                    result="success",
                )
                instance.register_applied_event(event)
                knowledge = Knowledge.record(
                    id=self._new_knowledge_id(),
                    world_instance_id=instance.id,
                    subject_type=SubjectType.NPC,
                    subject_id=str(npc.id),
                    information_id=information.id,
                    claim=claim,
                    claim_type=command.claim_type,
                    source=command.source,
                    source_ref=command.source_ref,
                    confidence=command.confidence,
                    acquired_at=now,
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
                    "npc_id": str(npc.id),
                    "information_key": information.key,
                    "claim": knowledge.claim,
                    "claim_type": knowledge.claim_type.value,
                    "source": knowledge.source.value,
                    "confidence": knowledge.confidence.value,
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)
