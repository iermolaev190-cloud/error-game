"""Unit: authored case content, instance case state, and theory resolution guards."""

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone

import pytest

from world_error.domain.investigations.case import (
    Case,
    CaseDefinition,
    CaseEvidenceRelevance,
    CaseNote,
    CaseNoteVisibility,
    CaseStatus,
    CaseTheory,
    CaseTheoryConfidence,
    CaseTheoryStatus,
    CaseVisibility,
    InitialEvidenceDefinition,
    ResolutionCriteria,
)
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    CaseId,
    CaseNoteId,
    CaseTheoryId,
    CharacterId,
    DomainError,
    ErrorCode,
    InformationId,
    KnowledgeId,
    WorldInstanceId,
    new_case_contradiction_link_id,
    new_case_evidence_link_id,
    new_case_id,
    new_case_note_id,
    new_case_question_id,
    new_case_suspect_link_id,
    new_case_theory_id,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
CHARACTER_ID = CharacterId("ch_anna")


def make_definition() -> CaseDefinition:
    return CaseDefinition(
        key="station_disappearance",
        question="Что произошло с исследователем?",
        opening_hint="Исследователь не вернулся со старой станции.",
        initial_evidence=(
            InitialEvidenceDefinition("damaged_radio", CaseEvidenceRelevance.UNKNOWN),
        ),
        resolution_criteria=ResolutionCriteria(
            required_evidence_count=3,
            required_theory_count=1,
            required_theory_min_confidence=CaseTheoryConfidence.PLAUSIBLE,
            required_distinct_contributors=2,
            required_actions=("mark_suspect",),
        ),
    )


def test_case_definition_is_immutable_authored_content() -> None:
    definition = make_definition()
    assert definition.key == "station_disappearance"
    assert definition.initial_evidence[0].information_key == "damaged_radio"
    with pytest.raises(FrozenInstanceError):
        definition.question = "Изменённый вопрос"  # type: ignore[misc]


def test_case_materializes_open_and_instance_scoped() -> None:
    case = Case.open(
        id=CaseId("case_station_disappearance"),
        world_instance_id=WORLD_ID,
        definition=make_definition(),
        now=NOW,
    )

    assert case.world_instance_id == WORLD_ID
    assert case.status is CaseStatus.OPEN
    assert case.current_question == make_definition().question
    assert case.created_at == case.updated_at == NOW
    assert CaseStatus.ABANDONED.value == "ABANDONED"


def test_resolution_criteria_reject_negative_counts() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        ResolutionCriteria(required_evidence_count=-1)


def test_confirmed_theory_requires_resolution_criteria() -> None:
    with pytest.raises(DomainError) as exc_info:
        CaseTheory.create(
            id=CaseTheoryId("th_1"),
            world_instance_id=WORLD_ID,
            case_id=CaseId("case_1"),
            author_id=CHARACTER_ID,
            claim="Смотритель скрыл журнал.",
            confidence=CaseTheoryConfidence.CONFIRMED,
            visibility=CaseVisibility.CASE_SHARED,
            now=NOW,
            status=CaseTheoryStatus.CONFIRMED,
        )
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_private_note_shape_is_append_only_and_has_no_public_visibility() -> None:
    note = CaseNote(
        id=CaseNoteId("note_1"),
        world_instance_id=WORLD_ID,
        case_id=CaseId("case_1"),
        author_id=CHARACTER_ID,
        text="Проверить запись в журнале.",
        visibility=CaseNoteVisibility.PRIVATE,
        created_at=NOW,
    )
    note_fields = {field.name for field in fields(CaseNote)}

    assert note.visibility is CaseNoteVisibility.PRIVATE
    assert "updated_at" not in note_fields
    assert "PUBLIC" not in {visibility.value for visibility in CaseNoteVisibility}


def test_investigation_ids_use_reserved_prefixes() -> None:
    assert new_case_id().startswith("case_")
    assert new_case_evidence_link_id().startswith("ev_")
    assert new_case_theory_id().startswith("th_")
    assert new_case_contradiction_link_id().startswith("ctr_")
    assert new_case_suspect_link_id().startswith("sus_")
    assert new_case_note_id().startswith("note_")
    assert new_case_question_id().startswith("q_")