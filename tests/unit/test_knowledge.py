"""Unit: Knowledge — claim берётся из контента, truth в знание не переносится."""

from __future__ import annotations

from datetime import datetime, timezone

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
    InformationId,
    KnowledgeId,
    LocationKey,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_test")

CONTENT = "Радио повреждено: корпус вскрыт, антенна сломана."
TRUTH = "Радио повреждено намеренно: антенну сломали изнутри."


def make_character() -> Character:
    return Character.create(
        id=CharacterId("ch_1"),
        world_instance_id=WORLD_ID,
        player_id="player-1",
        name="Аня",
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


def make_knowledge() -> Knowledge:
    return Knowledge.from_discovery(
        id=KnowledgeId("kn_1"),
        character=make_character(),
        information=make_information(),
        definition=make_definition(),
        now=NOW,
    )


def test_claim_comes_from_content_not_from_truth() -> None:
    knowledge = make_knowledge()
    assert knowledge.claim == CONTENT
    assert knowledge.claim != TRUTH
    assert "намеренно" not in knowledge.claim


def test_knowledge_metadata() -> None:
    knowledge = make_knowledge()
    assert knowledge.claim_type is ClaimType.FACT
    assert knowledge.source is KnowledgeSource.OBSERVATION
    assert knowledge.confidence is KnowledgeConfidence.LIKELY
    assert knowledge.subject_type is SubjectType.CHARACTER
    assert knowledge.subject_id == "ch_1"
    assert knowledge.source_ref == "ch_1"
    assert knowledge.information_id == InformationId("info_1")
    assert knowledge.acquired_at == NOW


def test_knowledge_belongs_to_character_world() -> None:
    knowledge = make_knowledge()
    assert knowledge.world_instance_id == WORLD_ID
