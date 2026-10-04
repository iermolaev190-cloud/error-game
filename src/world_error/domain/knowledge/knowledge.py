"""Знание: что субъект мира считает правдой.

Ключевое правило (MASTER_SPEC §3.7, CODING_RULES 8): знание ≠ истина мира.
``Knowledge`` строится из ``InformationDefinition.content`` или из знания другого
субъекта и никогда — из ``truth``. Знание неизменяемо: это запись о том, что
субъект узнал, а не состояние, которое переписывается.

Полиморфизм субъекта (``subject_type``) валидируется доменом: сейчас
используется только CHARACTER, в дальнейшем — NPC и FACTION (07_KNOWLEDGE).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from world_error.domain.characters.character import Character
from world_error.domain.information.information import Information, InformationDefinition
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    InformationId,
    KnowledgeId,
    WorldInstanceId,
)


class SubjectType(StrEnum):
    CHARACTER = "CHARACTER"
    NPC = "NPC"
    FACTION = "FACTION"


class ClaimType(StrEnum):
    """TRUTH / KNOWLEDGE / CLAIM / RUMOR / THEORY / BELIEF (19_MVP_V1_FOR_AI §13)."""

    FACT = "FACT"
    CLAIM = "CLAIM"
    RUMOR = "RUMOR"
    THEORY = "THEORY"
    BELIEF = "BELIEF"


class KnowledgeSource(StrEnum):
    """Откуда субъект узнал.

    ``CHARACTER`` — знание передано другим персонажем (SHARE): это не
    наблюдение и не документ, поэтому ``claim_type`` в таком знании всегда
    понижается до ``CLAIM``.
    """

    OBSERVATION = "OBSERVATION"
    DOCUMENT = "DOCUMENT"
    NPC = "NPC"
    CHARACTER = "CHARACTER"
    RUMOR = "RUMOR"
    HYPOTHESIS = "HYPOTHESIS"


class KnowledgeConfidence(StrEnum):
    """Уверенность вместо чисел (11_WORLD_STATE_V1 §7)."""

    UNCERTAIN = "UNCERTAIN"
    LIKELY = "LIKELY"
    CERTAIN = "CERTAIN"


@dataclass(frozen=True, slots=True)
class Knowledge:
    id: KnowledgeId
    world_instance_id: WorldInstanceId
    subject_type: SubjectType
    subject_id: str
    information_id: InformationId
    claim: str
    claim_type: ClaimType
    source: KnowledgeSource
    source_ref: str | None
    confidence: KnowledgeConfidence
    acquired_at: datetime
    document_date: date | None = None

    @classmethod
    def record(
        cls,
        *,
        id: KnowledgeId,
        world_instance_id: WorldInstanceId,
        subject_type: SubjectType,
        subject_id: str,
        information_id: InformationId,
        claim: str,
        claim_type: ClaimType,
        source: KnowledgeSource,
        source_ref: str | None,
        confidence: KnowledgeConfidence,
        acquired_at: datetime,
        document_date: date | None = None,
    ) -> "Knowledge":
        """Создать запись знания с валидацией.

        Общая фабрика для всех путей получения знания (наблюдение, передача от
        персонажа, позже — документы и NPC).

        Важно: фабрика намеренно **не принимает** ``InformationDefinition`` и не
        читает контент мира. Канонический факт (``truth``) не может попасть в
        знание даже случайно — у этой функции нет доступа к нему, только к тому,
        что субъект уже знает или наблюдал.

        ``claim_type``, ``source`` и ``confidence`` — строго перечисления
        (11_WORLD_STATE_V1 §7: состояния, а не произвольные числа и строки).
        """
        if not claim or not claim.strip():
            raise DomainError(ErrorCode.INVALID_ACTION, "knowledge claim must not be empty")
        if not subject_id:
            raise DomainError(ErrorCode.INVALID_ACTION, "knowledge subject must be identified")
        return cls(
            id=id,
            world_instance_id=world_instance_id,
            subject_type=subject_type,
            subject_id=subject_id,
            information_id=information_id,
            claim=claim,
            claim_type=claim_type,
            source=source,
            source_ref=source_ref,
            confidence=confidence,
            acquired_at=acquired_at,
            document_date=document_date,
        )

    @classmethod
    def from_observation(
        cls,
        *,
        id: KnowledgeId,
        world_instance_id: WorldInstanceId,
        subject_type: SubjectType,
        subject_id: str,
        information: Information,
        definition: InformationDefinition,
        now: datetime,
    ) -> "Knowledge":
        """Знание, полученное наблюдением (первичный источник).

        ``claim`` берётся из ``definition.content``; ``definition.truth`` здесь
        не участвует — иначе истина мира автоматически стала бы знанием
        субъекта. Работает и для персонажа, и для NPC.
        """
        return cls.record(
            id=id,
            world_instance_id=world_instance_id,
            subject_type=subject_type,
            subject_id=subject_id,
            information_id=information.id,
            claim=definition.content,
            claim_type=ClaimType.FACT,
            source=KnowledgeSource.OBSERVATION,
            source_ref=subject_id,
            confidence=KnowledgeConfidence.LIKELY,
            acquired_at=now,
            document_date=definition.document_date,
        )

    @classmethod
    def from_discovery(
        cls,
        *,
        id: KnowledgeId,
        character: Character,
        information: Information,
        definition: InformationDefinition,
        now: datetime,
    ) -> "Knowledge":
        """Наблюдение персонажем игрока (обёртка над ``from_observation``)."""
        return cls.from_observation(
            id=id,
            world_instance_id=character.world_instance_id,
            subject_type=SubjectType.CHARACTER,
            subject_id=str(character.id),
            information=information,
            definition=definition,
            now=now,
        )

    @classmethod
    def from_share(
        cls,
        *,
        id: KnowledgeId,
        sharer: Character,
        sharer_knowledge: Knowledge,
        receiver: Character,
        now: datetime,
    ) -> "Knowledge":
        """Знание, полученное от другого персонажа (SHARE).

        Правила:

        * ``claim`` копируется из знания sharer'а — не из ``truth`` и не из
          контента; контент в этот путь вообще не передаётся;
        * ``claim_type`` всегда ``CLAIM``: услышанное не является наблюдением;
        * ``source = CHARACTER``, ``source_ref = sharer.id`` — цепочка
          происхождения однозвенная (M3): произвольная длина достигается
          рекурсией по ``source_ref``, отдельное поле origin_ref не вводится;
        * ``subject_type`` у обоих — CHARACTER; расширение на NPC/FACTION
          появится вместе с их собственными путями передачи знания.
        """
        if sharer.world_instance_id != receiver.world_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                "characters belong to different world instances",
            )
        if sharer_knowledge.world_instance_id != receiver.world_instance_id:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                "shared knowledge belongs to another world instance",
            )
        if (
            sharer_knowledge.subject_type is not SubjectType.CHARACTER
            or sharer_knowledge.subject_id != str(sharer.id)
        ):
            raise DomainError(ErrorCode.NOT_ALLOWED, "only own knowledge can be shared")

        return cls.record(
            id=id,
            world_instance_id=receiver.world_instance_id,
            subject_type=SubjectType.CHARACTER,
            subject_id=str(receiver.id),
            information_id=sharer_knowledge.information_id,
            claim=sharer_knowledge.claim,
            claim_type=ClaimType.CLAIM,
            source=KnowledgeSource.CHARACTER,
            source_ref=str(sharer.id),
            confidence=KnowledgeConfidence.LIKELY,
            acquired_at=now,
            document_date=sharer_knowledge.document_date,
        )
