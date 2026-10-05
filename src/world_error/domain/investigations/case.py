"""Investigation case definitions and instance-scoped case records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from world_error.domain.events.event import Event, EventType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    CaseContradictionLinkId,
    CaseEvidenceLinkId,
    CaseId,
    CaseNoteId,
    CaseQuestionId,
    CaseTheoryId,
    CharacterId,
    DomainError,
    ErrorCode,
    InformationId,
    KnowledgeId,
    WorldInstanceId,
)


class CaseStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ABANDONED = "ABANDONED"
    UNRESOLVED = "UNRESOLVED"


class CaseEvidenceRelevance(StrEnum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class CaseTheoryConfidence(StrEnum):
    SPECULATIVE = "SPECULATIVE"
    PLAUSIBLE = "PLAUSIBLE"
    SUPPORTED = "SUPPORTED"
    CONFIRMED = "CONFIRMED"


class CaseTheoryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    CONFIRMED = "CONFIRMED"
    UNRESOLVED = "UNRESOLVED"


class CaseVisibility(StrEnum):
    PRIVATE = "PRIVATE"
    CASE_SHARED = "CASE_SHARED"


class CaseTheoryEvidenceStance(StrEnum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"


class CaseSuspectStatus(StrEnum):
    SUSPECTED = "SUSPECTED"
    CLEARED = "CLEARED"
    CONFIRMED = "CONFIRMED"
    UNKNOWN = "UNKNOWN"


class CaseNoteVisibility(StrEnum):
    PRIVATE = "PRIVATE"
    CASE_SHARED = "CASE_SHARED"


RESOLUTION_ACTIONS = frozenset(
    {
        "link_evidence",
        "create_theory",
        "link_theory_evidence",
        "mark_contradiction",
        "mark_suspect",
        "add_case_note",
        "add_case_question",
    }
)


@dataclass(frozen=True, slots=True)
class InitialEvidenceDefinition:
    information_key: str
    relevance: CaseEvidenceRelevance = CaseEvidenceRelevance.UNKNOWN


@dataclass(frozen=True, slots=True)
class ResolutionCriteria:
    required_evidence_count: int = 0
    required_theory_count: int = 0
    required_theory_min_confidence: CaseTheoryConfidence | None = None
    required_distinct_contributors: int = 0
    required_actions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.required_evidence_count < 0 or self.required_theory_count < 0:
            raise ValueError("resolution counts must not be negative")
        if self.required_distinct_contributors < 0:
            raise ValueError("required_distinct_contributors must not be negative")
        unknown_actions = set(self.required_actions) - RESOLUTION_ACTIONS
        if unknown_actions:
            raise ValueError(f"unknown required resolution actions: {sorted(unknown_actions)}")


@dataclass(frozen=True, slots=True)
class CaseDefinition:
    """Global authored content; contains references, never copied world facts."""

    key: str
    question: str
    opening_hint: str
    initial_evidence: tuple[InitialEvidenceDefinition, ...]
    resolution_criteria: ResolutionCriteria

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.question.strip():
            raise ValueError("case key and question must not be empty")
        if len({item.information_key for item in self.initial_evidence}) != len(
            self.initial_evidence
        ):
            raise ValueError("initial evidence information keys must be unique")


@dataclass(slots=True)
class Case:
    id: CaseId
    world_instance_id: WorldInstanceId
    key: str
    status: CaseStatus
    current_question: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def open(
        cls,
        *,
        id: CaseId,
        world_instance_id: WorldInstanceId,
        definition: CaseDefinition,
        now: datetime,
    ) -> "Case":
        return cls(
            id=id,
            world_instance_id=world_instance_id,
            key=definition.key,
            status=CaseStatus.OPEN,
            current_question=definition.question,
            created_at=now,
            updated_at=now,
        )

    def apply(self, event: Event) -> None:
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(ErrorCode.NOT_ALLOWED, "case event belongs to another instance")
        if str(event.payload.get("case_id")) != str(self.id):
            raise DomainError(ErrorCode.NOT_ALLOWED, "event targets another case")
        if event.type is EventType.CASE_QUESTION_ADDED:
            text = str(event.payload.get("text", ""))
            if not text.strip() or self.status is not CaseStatus.OPEN:
                raise DomainError(ErrorCode.INVALID_ACTION, "cannot add question to this case")
            if event.payload.get("previous_question") != self.current_question:
                raise DomainError(ErrorCode.CONFLICT, "case question changed since event was prepared")
            self.current_question = text
        elif event.type is EventType.CASE_CLOSED:
            if self.status is not CaseStatus.OPEN:
                raise DomainError(ErrorCode.INVALID_ACTION, f"case is already {self.status.value}")
            if event.payload.get("resolution_criteria_satisfied") is not True:
                raise DomainError(ErrorCode.INVALID_ACTION, "case resolution criteria are not satisfied")
            self.status = CaseStatus.CLOSED
        else:
            raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported case event: {event.type}")
        self.updated_at = event.executed_at or event.created_at


@dataclass(slots=True)
class CaseEvidenceLink:
    id: CaseEvidenceLinkId
    world_instance_id: WorldInstanceId
    case_id: CaseId
    information_id: InformationId
    knowledge_id: KnowledgeId | None
    relevance: CaseEvidenceRelevance
    added_by: CharacterId | None
    added_at: datetime

    def apply(self, event: Event) -> None:
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(ErrorCode.NOT_ALLOWED, "evidence event belongs to another instance")
        if event.type is not EventType.EVIDENCE_LINKED:
            raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported evidence event: {event.type}")
        if (
            str(event.payload.get("case_id")) != str(self.case_id)
            or str(event.payload.get("evidence_link_id")) != str(self.id)
        ):
            raise DomainError(ErrorCode.NOT_ALLOWED, "event targets another evidence link")
        previous = event.payload.get("previous_knowledge_id")
        if previous != (None if self.knowledge_id is None else str(self.knowledge_id)):
            raise DomainError(ErrorCode.CONFLICT, "evidence knowledge changed since event was prepared")
        knowledge_id = event.payload.get("knowledge_id")
        added_by = event.payload.get("added_by")
        if not knowledge_id or not added_by:
            raise DomainError(ErrorCode.INVALID_ACTION, "evidence link update requires knowledge and author")
        self.knowledge_id = KnowledgeId(str(knowledge_id))
        self.added_by = CharacterId(str(added_by))
        self.relevance = CaseEvidenceRelevance(str(event.payload.get("relevance", self.relevance.value)))
        self.added_at = event.executed_at or event.created_at


@dataclass(slots=True)
class CaseTheory:
    id: CaseTheoryId
    world_instance_id: WorldInstanceId
    case_id: CaseId
    author_id: CharacterId
    claim: str
    confidence: CaseTheoryConfidence
    visibility: CaseVisibility
    status: CaseTheoryStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        id: CaseTheoryId,
        world_instance_id: WorldInstanceId,
        case_id: CaseId,
        author_id: CharacterId,
        claim: str,
        confidence: CaseTheoryConfidence,
        visibility: CaseVisibility,
        now: datetime,
        status: CaseTheoryStatus = CaseTheoryStatus.ACTIVE,
    ) -> "CaseTheory":
        if not claim.strip():
            raise DomainError(ErrorCode.INVALID_ACTION, "theory claim must not be empty")
        if status is not CaseTheoryStatus.ACTIVE:
            raise DomainError(
                ErrorCode.INVALID_ACTION,
                "new case theories must start ACTIVE; status changes require case validation",
            )
        return cls(
            id=id,
            world_instance_id=world_instance_id,
            case_id=case_id,
            author_id=author_id,
            claim=claim,
            confidence=confidence,
            visibility=visibility,
            status=status,
            created_at=now,
            updated_at=now,
        )


@dataclass(frozen=True, slots=True)
class CaseTheoryEvidenceLink:
    world_instance_id: WorldInstanceId
    theory_id: CaseTheoryId
    evidence_link_id: CaseEvidenceLinkId
    stance: CaseTheoryEvidenceStance
    added_by: CharacterId
    added_at: datetime


@dataclass(frozen=True, slots=True)
class CaseContradictionLink:
    id: CaseContradictionLinkId
    world_instance_id: WorldInstanceId
    case_id: CaseId
    evidence_a_id: CaseEvidenceLinkId
    evidence_b_id: CaseEvidenceLinkId
    note: str
    marked_by: CharacterId
    marked_at: datetime


@dataclass(frozen=True, slots=True)
class CaseSuspectLink:
    id: CaseSuspectLinkId
    world_instance_id: WorldInstanceId
    case_id: CaseId
    subject_type: SubjectType
    subject_id: str
    reason: str
    marked_by: CharacterId
    status: CaseSuspectStatus
    marked_at: datetime

    def apply(self, event: Event) -> None:
        if event.world_instance_id != self.world_instance_id:
            raise DomainError(ErrorCode.NOT_ALLOWED, "suspect event belongs to another instance")
        if event.type is not EventType.SUSPECT_MARKED:
            raise DomainError(ErrorCode.INVALID_ACTION, f"unsupported suspect event: {event.type}")
        if (
            str(event.payload.get("case_id")) != str(self.case_id)
            or str(event.payload.get("suspect_link_id")) != str(self.id)
            or str(event.payload.get("subject_id")) != self.subject_id
            or str(event.payload.get("subject_type")) != self.subject_type.value
            or str(event.payload.get("marked_by")) != str(self.marked_by)
            or event.actor != str(self.marked_by)
        ):
            raise DomainError(ErrorCode.NOT_ALLOWED, "event targets another suspect link")
        try:
            self.status = CaseSuspectStatus(str(event.payload["status"]))
        except (KeyError, ValueError) as exc:
            raise DomainError(ErrorCode.INVALID_ACTION, "invalid suspect status") from exc
        self.reason = str(event.payload.get("reason", self.reason))
        self.marked_at = event.executed_at or event.created_at


@dataclass(frozen=True, slots=True)
class CaseNote:
    id: CaseNoteId
    world_instance_id: WorldInstanceId
    case_id: CaseId
    author_id: CharacterId
    text: str
    visibility: CaseNoteVisibility
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CaseQuestion:
    id: CaseQuestionId
    world_instance_id: WorldInstanceId
    case_id: CaseId
    text: str
    added_by: CharacterId
    created_at: datetime