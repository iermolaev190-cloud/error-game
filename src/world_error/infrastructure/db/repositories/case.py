"""Instance-scoped case, evidence, theory, suspect, note, and question repository."""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.investigations.case import (
    Case,
    CaseContradictionLink,
    CaseEvidenceLink,
    CaseNote,
    CaseQuestion,
    CaseSuspectLink,
    CaseTheory,
    CaseTheoryEvidenceLink,
)
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    CaseEvidenceLinkId,
    CaseId,
    CaseTheoryId,
    DomainError,
    ErrorCode,
    WorldInstanceId,
)
from world_error.infrastructure.db.repositories._mapping import (
    case_contradiction_link_from_row,
    case_contradiction_link_row,
    case_evidence_link_from_row,
    case_evidence_link_row,
    case_from_row,
    case_note_from_row,
    case_note_row,
    case_question_from_row,
    case_question_row,
    case_row,
    case_suspect_link_from_row,
    case_suspect_link_row,
    case_theory_evidence_link_from_row,
    case_theory_evidence_link_row,
    case_theory_from_row,
    case_theory_row,
)
from world_error.infrastructure.db.tables import (
    case_contradiction_links,
    case_evidence_links,
    case_notes,
    case_questions,
    case_suspect_links,
    case_theories,
    case_theory_evidence_links,
    cases,
)


class SqlCaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, case: Case) -> None:
        self._session.execute(insert(cases).values(**case_row(case)))

    def get(self, world_instance_id: WorldInstanceId, case_id: CaseId) -> Case:
        row = (
            self._session.execute(
                select(cases).where(
                    cases.c.world_instance_id == str(world_instance_id),
                    cases.c.id == str(case_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"case not found: {case_id}")
        return case_from_row(dict(row))

    def get_by_key(self, world_instance_id: WorldInstanceId, key: str) -> Case:
        row = (
            self._session.execute(
                select(cases).where(
                    cases.c.world_instance_id == str(world_instance_id),
                    cases.c.key == key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"case not found: {key}")
        return case_from_row(dict(row))

    def list_for_instance(self, world_instance_id: WorldInstanceId) -> list[Case]:
        rows = (
            self._session.execute(
                select(cases)
                .where(cases.c.world_instance_id == str(world_instance_id))
                .order_by(cases.c.key)
            )
            .mappings()
            .all()
        )
        return [case_from_row(dict(row)) for row in rows]

    def save(self, case: Case) -> None:
        result = self._session.execute(
            update(cases)
            .where(
                cases.c.world_instance_id == str(case.world_instance_id),
                cases.c.id == str(case.id),
            )
            .values(**case_row(case))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"case not found: {case.id}")

    def add_evidence_link(self, link: CaseEvidenceLink) -> None:
        self._session.execute(
            insert(case_evidence_links).values(**case_evidence_link_row(link))
        )

    def find_evidence_link(
        self, world_instance_id: WorldInstanceId, case_id: CaseId, information_id
    ) -> CaseEvidenceLink | None:  # noqa: ANN001
        row = (
            self._session.execute(
                select(case_evidence_links).where(
                    case_evidence_links.c.world_instance_id == str(world_instance_id),
                    case_evidence_links.c.case_id == str(case_id),
                    case_evidence_links.c.information_id == str(information_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else case_evidence_link_from_row(dict(row))

    def get_evidence_link(
        self, world_instance_id: WorldInstanceId, link_id: CaseEvidenceLinkId
    ) -> CaseEvidenceLink:
        row = (
            self._session.execute(
                select(case_evidence_links).where(
                    case_evidence_links.c.world_instance_id == str(world_instance_id),
                    case_evidence_links.c.id == str(link_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"case evidence link not found: {link_id}")
        return case_evidence_link_from_row(dict(row))

    def list_evidence(self, world_instance_id: WorldInstanceId, case_id: CaseId) -> list[CaseEvidenceLink]:
        rows = (
            self._session.execute(
                select(case_evidence_links)
                .where(
                    case_evidence_links.c.world_instance_id == str(world_instance_id),
                    case_evidence_links.c.case_id == str(case_id),
                )
                .order_by(case_evidence_links.c.added_at, case_evidence_links.c.id)
            )
            .mappings()
            .all()
        )
        return [case_evidence_link_from_row(dict(row)) for row in rows]

    def save_evidence_link(self, link: CaseEvidenceLink) -> None:
        result = self._session.execute(
            update(case_evidence_links)
            .where(
                case_evidence_links.c.world_instance_id == str(link.world_instance_id),
                case_evidence_links.c.id == str(link.id),
            )
            .values(**case_evidence_link_row(link))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"case evidence link not found: {link.id}")

    def add_theory(self, theory: CaseTheory) -> None:
        self._session.execute(insert(case_theories).values(**case_theory_row(theory)))

    def get_theory(self, world_instance_id: WorldInstanceId, theory_id: CaseTheoryId) -> CaseTheory:
        row = (
            self._session.execute(
                select(case_theories).where(
                    case_theories.c.world_instance_id == str(world_instance_id),
                    case_theories.c.id == str(theory_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"case theory not found: {theory_id}")
        return case_theory_from_row(dict(row))

    def list_theories(self, world_instance_id: WorldInstanceId, case_id: CaseId) -> list[CaseTheory]:
        rows = (
            self._session.execute(
                select(case_theories)
                .where(
                    case_theories.c.world_instance_id == str(world_instance_id),
                    case_theories.c.case_id == str(case_id),
                )
                .order_by(case_theories.c.created_at, case_theories.c.id)
            )
            .mappings()
            .all()
        )
        return [case_theory_from_row(dict(row)) for row in rows]

    def save_theory(self, theory: CaseTheory) -> None:
        result = self._session.execute(
            update(case_theories)
            .where(
                case_theories.c.world_instance_id == str(theory.world_instance_id),
                case_theories.c.id == str(theory.id),
            )
            .values(**case_theory_row(theory))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"case theory not found: {theory.id}")

    def add_theory_evidence_link(self, link: CaseTheoryEvidenceLink) -> None:
        self._session.execute(
            insert(case_theory_evidence_links).values(**case_theory_evidence_link_row(link))
        )

    def list_theory_evidence(self, world_instance_id: WorldInstanceId, theory_id: CaseTheoryId):
        rows = (
            self._session.execute(
                select(case_theory_evidence_links)
                .where(
                    case_theory_evidence_links.c.world_instance_id == str(world_instance_id),
                    case_theory_evidence_links.c.theory_id == str(theory_id),
                )
                .order_by(case_theory_evidence_links.c.evidence_link_id)
            )
            .mappings()
            .all()
        )
        return [case_theory_evidence_link_from_row(dict(row)) for row in rows]

    def add_contradiction(self, link: CaseContradictionLink) -> None:
        self._session.execute(
            insert(case_contradiction_links).values(**case_contradiction_link_row(link))
        )

    def list_contradictions(
        self, world_instance_id: WorldInstanceId, case_id: CaseId
    ) -> list[CaseContradictionLink]:
        rows = (
            self._session.execute(
                select(case_contradiction_links)
                .where(
                    case_contradiction_links.c.world_instance_id == str(world_instance_id),
                    case_contradiction_links.c.case_id == str(case_id),
                )
                .order_by(case_contradiction_links.c.marked_at, case_contradiction_links.c.id)
            )
            .mappings()
            .all()
        )
        return [case_contradiction_link_from_row(dict(row)) for row in rows]

    def find_suspect(
        self,
        world_instance_id: WorldInstanceId,
        case_id: CaseId,
        subject_type: SubjectType,
        subject_id: str,
    ) -> CaseSuspectLink | None:
        row = (
            self._session.execute(
                select(case_suspect_links).where(
                    case_suspect_links.c.world_instance_id == str(world_instance_id),
                    case_suspect_links.c.case_id == str(case_id),
                    case_suspect_links.c.subject_type == subject_type.value,
                    case_suspect_links.c.subject_id == subject_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else case_suspect_link_from_row(dict(row))

    def add_suspect(self, link: CaseSuspectLink) -> None:
        self._session.execute(insert(case_suspect_links).values(**case_suspect_link_row(link)))

    def save_suspect(self, link: CaseSuspectLink) -> None:
        result = self._session.execute(
            update(case_suspect_links)
            .where(
                case_suspect_links.c.world_instance_id == str(link.world_instance_id),
                case_suspect_links.c.id == str(link.id),
            )
            .values(**case_suspect_link_row(link))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"case suspect not found: {link.id}")

    def list_suspects(
        self, world_instance_id: WorldInstanceId, case_id: CaseId
    ) -> list[CaseSuspectLink]:
        rows = (
            self._session.execute(
                select(case_suspect_links)
                .where(
                    case_suspect_links.c.world_instance_id == str(world_instance_id),
                    case_suspect_links.c.case_id == str(case_id),
                )
                .order_by(case_suspect_links.c.marked_at, case_suspect_links.c.id)
            )
            .mappings()
            .all()
        )
        return [case_suspect_link_from_row(dict(row)) for row in rows]

    def add_note(self, note: CaseNote) -> None:
        self._session.execute(insert(case_notes).values(**case_note_row(note)))

    def list_notes(self, world_instance_id: WorldInstanceId, case_id: CaseId) -> list[CaseNote]:
        rows = (
            self._session.execute(
                select(case_notes)
                .where(
                    case_notes.c.world_instance_id == str(world_instance_id),
                    case_notes.c.case_id == str(case_id),
                )
                .order_by(case_notes.c.created_at, case_notes.c.id)
            )
            .mappings()
            .all()
        )
        return [case_note_from_row(dict(row)) for row in rows]

    def add_question(self, question: CaseQuestion) -> None:
        self._session.execute(insert(case_questions).values(**case_question_row(question)))

    def list_questions(self, world_instance_id: WorldInstanceId, case_id: CaseId) -> list[CaseQuestion]:
        rows = (
            self._session.execute(
                select(case_questions)
                .where(
                    case_questions.c.world_instance_id == str(world_instance_id),
                    case_questions.c.case_id == str(case_id),
                )
                .order_by(case_questions.c.created_at, case_questions.c.id)
            )
            .mappings()
            .all()
        )
        return [case_question_from_row(dict(row)) for row in rows]