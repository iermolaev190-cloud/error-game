"""Знание: что субъект мира считает правдой.

Ключевое правило (MASTER_SPEC §3.7, CODING_RULES 8): знание ≠ истина мира.
``Knowledge`` строится из ``InformationDefinition.content`` и никогда — из
``truth``. Знание неизменяемо: это запись о том, что субъект узнал, а не
состояние, которое переписывается.

Полиморфизм субъекта (``subject_type``) валидируется доменом: сейчас
используется только CHARACTER, в дальнейшем — NPC и FACTION (07_KNOWLEDGE).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from world_error.domain.characters.character import Character
from world_error.domain.information.information import Information, InformationDefinition
from world_error.domain.shared.kernel import (
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
    OBSERVATION = "OBSERVATION"
    DOCUMENT = "DOCUMENT"
    NPC = "NPC"
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
        """Знание, полученное наблюдением.

        ``claim`` берётся из ``definition.content``. ``definition.truth`` здесь
        не участвует — иначе истина мира автоматически стала бы знанием игрока.
        """
        return cls(
            id=id,
            world_instance_id=character.world_instance_id,
            subject_type=SubjectType.CHARACTER,
            subject_id=str(character.id),
            information_id=information.id,
            claim=definition.content,
            claim_type=ClaimType.FACT,
            source=KnowledgeSource.OBSERVATION,
            source_ref=str(character.id),
            confidence=KnowledgeConfidence.LIKELY,
            acquired_at=now,
        )
