"""Unit: Knowledge — валидация записи, все типы claim и правила SHARE."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from world_error.domain.characters.character import Character
from world_error.domain.information.information import Information, InformationDefinition
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    InformationId,
    KnowledgeId,
    LocationKey,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")
OTHER_WORLD_ID = WorldInstanceId("wi_other")
CONTENT = "Радио повреждено: корпус вскрыт, антенна сломана."
TRUTH = "Радио повреждено намеренно: антенну сломали изнутри."


def make_character(
    character_id: str = "ch_1", *, world_instance_id: WorldInstanceId = WORLD_ID
) -> Character:
    return Character.create(
        id=CharacterId(character_id),
        world_instance_id=world_instance_id,
        player_id=f"player-{character_id}",
        name=character_id,
        location_key=LocationKey("old_station"),
        now=NOW,
    )


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


def make_discovered_knowledge(character_id: str = "ch_1") -> Knowledge:
    return Knowledge.from_discovery(
        id=KnowledgeId("kn_1"),
        character=make_character(character_id),
        information=make_information(),
        definition=make_definition(),
        now=NOW,
    )


# --- наблюдение (коммит 2) -------------------------------------------------


def test_claim_comes_from_content_not_from_truth() -> None:
    knowledge = make_discovered_knowledge()
    assert knowledge.claim == CONTENT
    assert knowledge.claim != TRUTH
    assert "намеренно" not in knowledge.claim


def test_knowledge_metadata() -> None:
    knowledge = make_discovered_knowledge()
    assert knowledge.claim_type is ClaimType.FACT
    assert knowledge.source is KnowledgeSource.OBSERVATION
    assert knowledge.confidence is KnowledgeConfidence.LIKELY
    assert knowledge.subject_type is SubjectType.CHARACTER
    assert knowledge.subject_id == "ch_1"
    assert knowledge.source_ref == "ch_1"
    assert knowledge.information_id == InformationId("info_1")
    assert knowledge.acquired_at == NOW


def test_knowledge_belongs_to_character_world() -> None:
    assert make_discovered_knowledge().world_instance_id == WORLD_ID


# --- общая фабрика record (коммит 3a) --------------------------------------


def test_claim_type_has_all_five_values() -> None:
    assert {claim_type.value for claim_type in ClaimType} == {
        "FACT",
        "CLAIM",
        "RUMOR",
        "THEORY",
        "BELIEF",
    }


def test_knowledge_source_has_character_value() -> None:
    assert KnowledgeSource.CHARACTER.value == "CHARACTER"


@pytest.mark.parametrize("claim_type", list(ClaimType))
def test_record_supports_every_claim_type(claim_type: ClaimType) -> None:
    knowledge = Knowledge.record(
        id=KnowledgeId(f"kn_{claim_type.value.lower()}"),
        world_instance_id=WORLD_ID,
        subject_type=SubjectType.CHARACTER,
        subject_id="ch_1",
        information_id=InformationId("info_1"),
        claim=CONTENT,
        claim_type=claim_type,
        source=KnowledgeSource.OBSERVATION,
        source_ref="ch_1",
        confidence=KnowledgeConfidence.LIKELY,
        acquired_at=NOW,
    )
    assert knowledge.claim_type is claim_type
    assert knowledge.claim == CONTENT


def test_record_rejects_empty_claim() -> None:
    with pytest.raises(DomainError) as exc_info:
        Knowledge.record(
            id=KnowledgeId("kn_bad"),
            world_instance_id=WORLD_ID,
            subject_type=SubjectType.CHARACTER,
            subject_id="ch_1",
            information_id=InformationId("info_1"),
            claim="   ",
            claim_type=ClaimType.FACT,
            source=KnowledgeSource.OBSERVATION,
            source_ref="ch_1",
            confidence=KnowledgeConfidence.LIKELY,
            acquired_at=NOW,
        )
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


def test_record_rejects_empty_subject() -> None:
    with pytest.raises(DomainError) as exc_info:
        Knowledge.record(
            id=KnowledgeId("kn_bad"),
            world_instance_id=WORLD_ID,
            subject_type=SubjectType.CHARACTER,
            subject_id="",
            information_id=InformationId("info_1"),
            claim=CONTENT,
            claim_type=ClaimType.FACT,
            source=KnowledgeSource.OBSERVATION,
            source_ref=None,
            confidence=KnowledgeConfidence.LIKELY,
            acquired_at=NOW,
        )
    assert exc_info.value.code is ErrorCode.INVALID_ACTION


# --- from_share (коммит 3a) ------------------------------------------------


def make_shared_knowledge() -> Knowledge:
    return Knowledge.from_share(
        id=KnowledgeId("kn_shared"),
        sharer=make_character("ch_1"),
        sharer_knowledge=make_discovered_knowledge("ch_1"),
        receiver=make_character("ch_2"),
        now=NOW,
    )


def test_from_share_copies_claim_and_downgrades_to_claim() -> None:
    knowledge = make_shared_knowledge()
    assert knowledge.claim == CONTENT
    assert knowledge.claim != TRUTH
    assert knowledge.claim_type is ClaimType.CLAIM
    assert knowledge.subject_id == "ch_2"


def test_from_share_records_provenance() -> None:
    knowledge = make_shared_knowledge()
    assert knowledge.source is KnowledgeSource.CHARACTER
    assert knowledge.source_ref == "ch_1"
    assert knowledge.confidence is KnowledgeConfidence.LIKELY
    assert knowledge.information_id == InformationId("info_1")
    assert knowledge.world_instance_id == WORLD_ID
    assert knowledge.acquired_at == NOW


def test_from_share_rejects_characters_from_different_instances() -> None:
    with pytest.raises(DomainError) as exc_info:
        Knowledge.from_share(
            id=KnowledgeId("kn_shared"),
            sharer=make_character("ch_1"),
            sharer_knowledge=make_discovered_knowledge("ch_1"),
            receiver=make_character("ch_2", world_instance_id=OTHER_WORLD_ID),
            now=NOW,
        )
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_from_share_rejects_knowledge_from_another_instance() -> None:
    with pytest.raises(DomainError) as exc_info:
        Knowledge.from_share(
            id=KnowledgeId("kn_shared"),
            sharer=make_character("ch_1"),
            sharer_knowledge=Knowledge.record(
                id=KnowledgeId("kn_foreign"),
                world_instance_id=OTHER_WORLD_ID,
                subject_type=SubjectType.CHARACTER,
                subject_id="ch_1",
                information_id=InformationId("info_1"),
                claim=CONTENT,
                claim_type=ClaimType.FACT,
                source=KnowledgeSource.OBSERVATION,
                source_ref="ch_1",
                confidence=KnowledgeConfidence.LIKELY,
                acquired_at=NOW,
            ),
            receiver=make_character("ch_2"),
            now=NOW,
        )
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED


def test_from_share_rejects_knowledge_of_another_character() -> None:
    with pytest.raises(DomainError) as exc_info:
        Knowledge.from_share(
            id=KnowledgeId("kn_shared"),
            sharer=make_character("ch_1"),
            sharer_knowledge=make_discovered_knowledge("ch_3"),
            receiver=make_character("ch_2"),
            now=NOW,
        )
    assert exc_info.value.code is ErrorCode.NOT_ALLOWED
