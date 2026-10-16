"""Public case views and viewer-filtered private theories/notes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.investigations.case import (
    CaseNoteVisibility,
    CaseTheoryEvidenceStance,
    CaseVisibility,
)
from world_error.domain.shared.kernel import CaseId, CharacterId, DomainError, ErrorCode, WorldInstanceId


@dataclass(frozen=True, slots=True)
class CaseView:
    world_instance_id: str
    case_id: str
    key: str
    status: str
    question: str
    opening_hint: str


@dataclass(frozen=True, slots=True)
class CaseEvidenceView:
    evidence_link_id: str
    information_key: str
    relevance: str
    claim: str | None
    added_by: str | None


@dataclass(frozen=True, slots=True)
class CaseTheoryEvidenceView:
    evidence_link_id: str
    stance: str


@dataclass(frozen=True, slots=True)
class CaseTheoryView:
    theory_id: str
    author_id: str
    claim: str
    confidence: str
    status: str
    evidence: tuple[CaseTheoryEvidenceView, ...]


@dataclass(frozen=True, slots=True)
class CaseNoteView:
    note_id: str
    author_id: str
    text: str


@dataclass(frozen=True, slots=True)
class CaseSuspectView:
    subject_type: str
    subject_id: str
    reason: str
    marked_by: str
    status: str


class CaseViewQuery:
    def __init__(self, uow_factory: UnitOfWorkFactory, catalog: ContentCatalog) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog

    def get_case(
        self,
        world_instance_id: WorldInstanceId,
        case_id: CaseId,
        *,
        viewer_id: CharacterId,
    ) -> CaseView:
        with self._uow_factory() as uow:
            uow.characters.get(world_instance_id, viewer_id)
            case = uow.cases.get(world_instance_id, case_id)
            definition = self._catalog.case_definition(case.key)
            return self._case_view(case, definition.opening_hint)

    def list_cases(
        self, world_instance_id: WorldInstanceId, *, viewer_id: CharacterId
    ) -> tuple[CaseView, ...]:
        with self._uow_factory() as uow:
            uow.characters.get(world_instance_id, viewer_id)
            return tuple(
                self._case_view(case, self._catalog.case_definition(case.key).opening_hint)
                for case in uow.cases.list_for_instance(world_instance_id)
            )

    def get_case_evidence(
        self,
        world_instance_id: WorldInstanceId,
        case_id: CaseId,
        *,
        viewer_id: CharacterId,
    ) -> tuple[CaseEvidenceView, ...]:
        with self._uow_factory() as uow:
            uow.characters.get(world_instance_id, viewer_id)
            uow.cases.get(world_instance_id, case_id)
            views = []
            for link in uow.cases.list_evidence(world_instance_id, case_id):
                information = uow.information.get(world_instance_id, link.information_id)
                knowledge = (
                    None
                    if link.knowledge_id is None
                    else uow.knowledge.get(world_instance_id, link.knowledge_id)
                )
                views.append(
                    CaseEvidenceView(
                        evidence_link_id=str(link.id),
                        information_key=information.key,
                        relevance=link.relevance.value,
                        claim=None if knowledge is None else knowledge.claim,
                        added_by=None if link.added_by is None else str(link.added_by),
                    )
                )
            return tuple(views)

    def get_case_theories(
        self,
        world_instance_id: WorldInstanceId,
        case_id: CaseId,
        *,
        viewer_id: CharacterId,
    ) -> tuple[CaseTheoryView, ...]:
        with self._uow_factory() as uow:
            uow.characters.get(world_instance_id, viewer_id)
            uow.cases.get(world_instance_id, case_id)
            views = []
            for theory in uow.cases.list_theories(world_instance_id, case_id):
                if theory.visibility is CaseVisibility.PRIVATE and theory.author_id != viewer_id:
                    continue
                links = uow.cases.list_theory_evidence(world_instance_id, theory.id)
                views.append(
                    CaseTheoryView(
                        theory_id=str(theory.id),
                        author_id=str(theory.author_id),
                        claim=theory.claim,
                        confidence=theory.confidence.value,
                        status=theory.status.value,
                        evidence=tuple(
                            CaseTheoryEvidenceView(
                                evidence_link_id=str(link.evidence_link_id),
                                stance=link.stance.value,
                            )
                            for link in links
                        ),
                    )
                )
            return tuple(views)

    def get_case_notes(
        self,
        world_instance_id: WorldInstanceId,
        case_id: CaseId,
        *,
        viewer_id: CharacterId,
    ) -> tuple[CaseNoteView, ...]:
        with self._uow_factory() as uow:
            uow.characters.get(world_instance_id, viewer_id)
            uow.cases.get(world_instance_id, case_id)
            return tuple(
                CaseNoteView(note_id=str(note.id), author_id=str(note.author_id), text=note.text)
                for note in uow.cases.list_notes(world_instance_id, case_id)
                if note.visibility is CaseNoteVisibility.CASE_SHARED or note.author_id == viewer_id
            )

    def get_case_suspects(
        self,
        world_instance_id: WorldInstanceId,
        case_id: CaseId,
        *,
        viewer_id: CharacterId,
    ) -> tuple[CaseSuspectView, ...]:
        with self._uow_factory() as uow:
            uow.characters.get(world_instance_id, viewer_id)
            uow.cases.get(world_instance_id, case_id)
            return tuple(
                CaseSuspectView(
                    subject_type=suspect.subject_type.value,
                    subject_id=suspect.subject_id,
                    reason=suspect.reason,
                    marked_by=str(suspect.marked_by),
                    status=suspect.status.value,
                )
                for suspect in uow.cases.list_suspects(world_instance_id, case_id)
            )

    @staticmethod
    def _case_view(case, opening_hint: str) -> CaseView:  # noqa: ANN001
        return CaseView(
            world_instance_id=str(case.world_instance_id),
            case_id=str(case.id),
            key=case.key,
            status=case.status.value,
            question=case.current_question,
            opening_hint=opening_hint,
        )