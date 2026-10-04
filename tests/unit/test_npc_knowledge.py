"""Unit: знание NPC — общая фабрика, граница знания и право на ошибку."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from world_error.domain.information.information import Information, InformationDefinition
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.shared.kernel import (
    DomainError,
    ErrorCode,
    InformationId,
    KnowledgeId,
    LocationKey,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
NPC_ID = "npc_mechanic"
CONTENT = "Радио повреждено: корпус вскрыт, антенна сломана."
TRUTH = "Радио повреждено намеренно: антенну сломали изнутри."


def make_information() -> Information:
    return Information(
        id=InformationId("info_1"),
        world_instance_id=WORLD_ID,
        key="damaged_radio",
        location_key=LocationKey("old_station"),
        created_at=NOW,
    )


def make_definition() -> InformationDefinition:
    return InformationDefinition(
        key="damaged_radio",
        location_key=LocationKey("old_station"),
        information_type="DEVICE",
        source="PHYSICAL_OBJECT",
        authenticity="AUTHENTIC",
        access="OPEN",
        content=CONTENT,
        truth=TRUTH,
    )


def make_npc_knowledge() -> Knowledge:
    return Knowledge.from_observation(
        id=KnowledgeId("kn_npc"),
        world_instance_id=WORLD_ID,
        subject_type=SubjectType.NPC,
        subject_id=NPC_ID,
        information=make_information(),
        definition=make_definition(),
        now=NOW,
    )


def test_observation_creates_npc_knowledge_from_content_not_truth() -> None:
    knowledge = make_npc_knowledge()
    assert knowledge.subject_type is SubjectType.NPC
    assert knowledge.subject_id == NPC_ID
    assert knowledge.claim == CONTENT
    assert knowledge.claim != TRUTH
    assert "намеренно" not in knowledge.claim
    assert knowledge.claim_type is ClaimType.FACT
    assert knowledge.source is KnowledgeSource.OBSERVATION
    assert knowledge.source_ref == NPC_ID
    assert knowledge.confidence is KnowledgeConfidence.LIKELY
    assert knowledge.acquired_at == NOW


def test_npc_belief_can_differ_from_truth() -> None:
    """NPC может ошибаться: его версия — claim, а не канонический факт."""
    belief = Knowledge.record(
        id=KnowledgeId("kn_belief"),
        world_instance_id=WORLD_ID,
        subject_type=SubjectType.NPC,
        subject_id=NPC_ID,
        information_id=InformationId("info_1"),
        claim="Радио сломала гроза.",
        claim_type=ClaimType.THEORY,
        source=KnowledgeSource.HYPOTHESIS,
        source_ref=NPC_ID,
        confidence=KnowledgeConfidence.UNCERTAIN,
        acquired_at=NOW,
    )
    assert belief.claim != CONTENT
    assert belief.claim != TRUTH
    assert belief.claim_type is ClaimType.THEORY
    assert belief.confidence is KnowledgeConfidence.UNCERTAIN


def test_empty_claim_is_rejected() -> None:
    with pytest.raises(DomainError) as exc_info:
        Knowledge.record(
            id=KnowledgeId("kn_bad"),
            world_instance_id=WORLD_ID,
            subject_type=SubjectType.NPC,
            subject_id=NPC_ID,
            information_id=InformationId("info_1"),
            claim="   ",
            claim_type=ClaimType.FACT,
            source=KnowledgeSource.OBSERVATION,
            source_ref=NPC_ID,
            confidence=KnowledgeConfidence.LIKELY,
            acquired_at=NOW,
        )
    assert exc_info.value.code is ErrorCode.INVALID_ACTION
