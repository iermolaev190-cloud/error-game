"""Integration: case materialization, collaborative investigation, and persistence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.events.event import EventType
from world_error.domain.investigations.case import (
    CaseEvidenceRelevance,
    CaseNoteVisibility,
    CaseTheoryConfidence,
    CaseTheoryEvidenceStance,
    CaseVisibility,
)
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import (
    CaseEvidenceLinkId,
    CaseId,
    CaseTheoryId,
    CharacterId,
    DomainError,
    ErrorCode,
    EventId,
    LocationKey,
    WorldInstanceId,
)
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

CASE_KEY = "station_signal"
ROUTES = {
    LocationKey("base"): (LocationKey("base"),),
    LocationKey("forest"): (LocationKey("forest"),),
    LocationKey("old_station"): (LocationKey("forest"), LocationKey("old_station")),
}


def create_character(world_engine: WorldEngine, instance_id: WorldInstanceId, player: str) -> CharacterId:
    result = world_engine.create_character(instance_id, player_id=player, name=player)
    assert result.ok, result.error
    return CharacterId(result.payload["character_id"])


def case_id_for(
    world_engine: WorldEngine, instance_id: WorldInstanceId, viewer_id: CharacterId
) -> CaseId:
    cases = world_engine.list_cases(instance_id, viewer_id=viewer_id)
    case = next(item for item in cases if item.key == CASE_KEY)
    return CaseId(case.case_id)


def learn_information(
    world_engine: WorldEngine,
    instance_id: WorldInstanceId,
    character_id: CharacterId,
    information_key: str,
) -> None:
    character = world_engine.get_character(instance_id, character_id)
    target = world_engine.get_information(instance_id, information_key).location_key
    route = ROUTES[target]
    current = character.location_key
    if current == LocationKey("base") and target != LocationKey("base"):
        route = ROUTES[target]
    elif current == LocationKey("forest") and target == LocationKey("old_station"):
        route = (LocationKey("old_station"),)
    elif current == LocationKey("old_station") and target == LocationKey("forest"):
        route = (LocationKey("forest"),)
    elif current != target:
        route = ROUTES[target]
    for location in route:
        if world_engine.get_character(instance_id, character_id).location_key != location:
            moved = world_engine.move_character(
                instance_id, character_id=character_id, to_location_key=location
            )
            assert moved.ok, moved.error
    inspected = world_engine.inspect_information(
        instance_id, character_id=character_id, target_key=information_key
    )
    assert inspected.ok, inspected.error


def evidence_link(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    instance_id: WorldInstanceId,
    case_id: CaseId,
    information_id,
):
    with uow_factory() as uow:
        link = uow.cases.find_evidence_link(instance_id, case_id, information_id)
        assert link is not None
        return link


def test_instance_creation_materializes_isolated_cases_and_evidence(
    world_engine: WorldEngine,
) -> None:
    first = world_engine.create_instance(telegram_chat_id=-1001, seed=1)
    second = world_engine.create_instance(telegram_chat_id=-1002, seed=2)
    first_character = create_character(world_engine, first.id, "player-a")
    second_character = create_character(world_engine, second.id, "player-b")

    first_case_id = case_id_for(world_engine, first.id, first_character)
    second_case_id = case_id_for(world_engine, second.id, second_character)
    first_case = world_engine.get_case(first.id, first_case_id, viewer_id=first_character)
    second_case = world_engine.get_case(second.id, second_case_id, viewer_id=second_character)

    assert first_case.key == second_case.key == CASE_KEY
    assert first_case.case_id != second_case.case_id
    assert first_case.status == second_case.status == "OPEN"
    first_evidence = world_engine.get_case_evidence(first.id, first_case_id, viewer_id=first_character)
    second_evidence = world_engine.get_case_evidence(second.id, second_case_id, viewer_id=second_character)
    assert [item.information_key for item in first_evidence] == ["damaged_radio"]
    assert [item.information_key for item in second_evidence] == ["damaged_radio"]
    assert first_evidence[0].evidence_link_id != second_evidence[0].evidence_link_id

    with pytest.raises(DomainError) as exc_info:
        world_engine.get_case(second.id, first_case_id, viewer_id=second_character)
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_case_actions_link_claim_theory_contradiction_suspects_and_questions(
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    alice = create_character(world_engine, instance.id, "alice")
    bob = create_character(world_engine, instance.id, "bob")
    case_id = case_id_for(world_engine, instance.id, alice)
    radio = world_engine.get_information(instance.id, "damaged_radio")
    dispatch = world_engine.get_information(instance.id, "dispatch_log")
    station_test = world_engine.get_information(instance.id, "station_test_log")

    learn_information(world_engine, instance.id, alice, "damaged_radio")
    learned_radio = world_engine.get_knowledge(instance.id, alice)[0]
    radio_link = evidence_link(uow_factory, instance.id, case_id, radio.id)
    assert radio_link.knowledge_id is None

    linked_radio = world_engine.link_evidence(
        instance.id,
        case_id=case_id,
        actor_id=alice,
        information_id=radio.id,
        relevance=CaseEvidenceRelevance.SUPPORTING,
    )
    assert linked_radio.ok, linked_radio.error
    updated_radio = evidence_link(uow_factory, instance.id, case_id, radio.id)
    assert updated_radio.id == radio_link.id
    assert updated_radio.knowledge_id == learned_radio.id
    assert updated_radio.added_by == alice
    assert updated_radio.relevance is CaseEvidenceRelevance.SUPPORTING

    learn_information(world_engine, instance.id, bob, "dispatch_log")
    linked_dispatch = world_engine.link_evidence(
        instance.id, case_id=case_id, actor_id=bob, information_id=dispatch.id
    )
    assert linked_dispatch.ok, linked_dispatch.error
    dispatch_link = evidence_link(uow_factory, instance.id, case_id, dispatch.id)

    speculative = world_engine.create_theory(
        instance.id,
        case_id=case_id,
        author_id=alice,
        claim="Запись была изменена после потери связи.",
        confidence=CaseTheoryConfidence.CONFIRMED,
        visibility=CaseVisibility.CASE_SHARED,
    )
    assert speculative.ok, speculative.error
    theory_id = CaseTheoryId(speculative.payload["theory_id"])
    theory = world_engine.get_case_theories(instance.id, case_id, viewer_id=bob)[0]
    assert theory.status == "ACTIVE"
    assert theory.confidence == "CONFIRMED"

    theory_link = world_engine.link_theory_evidence(
        instance.id,
        case_id=case_id,
        actor_id=alice,
        theory_id=theory_id,
        evidence_link_id=radio_link.id,
        stance=CaseTheoryEvidenceStance.SUPPORTING,
    )
    assert theory_link.ok, theory_link.error
    contradiction = world_engine.mark_contradiction(
        instance.id,
        case_id=case_id,
        actor_id=bob,
        evidence_a_id=radio_link.id,
        evidence_b_id=dispatch_link.id,
        note="Временные отметки в двух источниках расходятся.",
    )
    assert contradiction.ok, contradiction.error

    npc = next(item for item in world_engine.get_npcs(instance.id) if item.key == "mechanic")
    faction = next(item for item in world_engine.get_factions(instance.id) if item.key == "council")
    suspects = (
        (SubjectType.CHARACTER, str(bob)),
        (SubjectType.NPC, str(npc.id)),
        (SubjectType.FACTION, str(faction.id)),
    )
    for subject_type, subject_id in suspects:
        result = world_engine.mark_suspect(
            instance.id,
            case_id=case_id,
            actor_id=alice,
            subject_type=subject_type,
            subject_id=subject_id,
            reason=f"Связь с источником: {subject_id}",
        )
        assert result.ok, result.error
    assert {
        (item.subject_type, item.subject_id)
        for item in world_engine.get_case_suspects(instance.id, case_id, viewer_id=bob)
    } == {(kind.value, subject_id) for kind, subject_id in suspects}

    learn_information(world_engine, instance.id, alice, "station_test_log")
    linked_test = world_engine.link_evidence(
        instance.id, case_id=case_id, actor_id=alice, information_id=station_test.id
    )
    assert linked_test.ok, linked_test.error
    test_link = evidence_link(uow_factory, instance.id, case_id, station_test.id)
    assert test_link.id not in {radio_link.id, dispatch_link.id}

    question_one = world_engine.add_case_question(
        instance.id, case_id=case_id, added_by=alice, text="Кто изменил журнал?"
    )
    question_two = world_engine.add_case_question(
        instance.id, case_id=case_id, added_by=bob, text="Когда это произошло?"
    )
    assert question_one.ok and question_two.ok
    assert world_engine.get_case(instance.id, case_id, viewer_id=alice).question == "Когда это произошло?"
    with uow_factory() as uow:
        questions = uow.cases.list_questions(instance.id, case_id)
    assert [item.text for item in questions] == ["Кто изменил журнал?", "Когда это произошло?"]
    assert len({item.id for item in questions}) == 2

    event_types = [item.type for item in world_engine.get_events(instance.id)]
    assert EventType.EVIDENCE_LINKED in event_types
    assert EventType.THEORY_CREATED in event_types
    assert EventType.THEORY_EVIDENCE_LINKED in event_types
    assert EventType.CONTRADICTION_MARKED in event_types
    assert EventType.SUSPECT_MARKED in event_types
    assert event_types.count(EventType.CASE_QUESTION_ADDED) == 2


def test_private_and_shared_notes_are_viewer_filtered_and_append_only(
    world_engine: WorldEngine, uow_factory: Callable[[], SqlAlchemyUnitOfWork]
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    alice = create_character(world_engine, instance.id, "alice")
    bob = create_character(world_engine, instance.id, "bob")
    case_id = case_id_for(world_engine, instance.id, alice)

    private = world_engine.add_case_note(
        instance.id, case_id=case_id, author_id=alice, text="Личная заметка", visibility=CaseNoteVisibility.PRIVATE
    )
    shared = world_engine.add_case_note(
        instance.id,
        case_id=case_id,
        author_id=alice,
        text="Общая заметка",
        visibility=CaseNoteVisibility.CASE_SHARED,
    )
    assert private.ok and shared.ok
    assert [note.text for note in world_engine.get_case_notes(instance.id, case_id, viewer_id=alice)] == [
        "Личная заметка",
        "Общая заметка",
    ]
    assert [note.text for note in world_engine.get_case_notes(instance.id, case_id, viewer_id=bob)] == [
        "Общая заметка"
    ]
    with uow_factory() as uow:
        notes = uow.cases.list_notes(instance.id, case_id)
    assert len(notes) == 2
    assert len({note.id for note in notes}) == 2
    note_events = [
        event
        for event in world_engine.get_events(instance.id)
        if event.type is EventType.CASE_NOTE_ADDED
    ]
    assert [event.payload["text"] for event in note_events] == [
        "Личная заметка",
        "Общая заметка",
    ]


def test_case_close_requires_resolution_criteria_and_distinct_contributors(
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    alice = create_character(world_engine, instance.id, "alice")
    bob = create_character(world_engine, instance.id, "bob")
    case_id = case_id_for(world_engine, instance.id, alice)

    rejected = world_engine.close_case(instance.id, case_id=case_id, actor_id=alice)
    assert not rejected.ok
    assert rejected.error is not None and rejected.error.code is ErrorCode.INVALID_ACTION
    assert world_engine.get_case(instance.id, case_id, viewer_id=alice).status == "OPEN"

    for information_key, actor in (
        ("damaged_radio", alice),
        ("dispatch_log", bob),
        ("station_test_log", alice),
    ):
        learn_information(world_engine, instance.id, actor, information_key)
        linked = world_engine.link_evidence(
            instance.id,
            case_id=case_id,
            actor_id=actor,
            information_id=world_engine.get_information(instance.id, information_key).id,
        )
        assert linked.ok, linked.error
    theory = world_engine.create_theory(
        instance.id,
        case_id=case_id,
        author_id=bob,
        claim="Нарушение произошло во время проверки.",
        confidence=CaseTheoryConfidence.PLAUSIBLE,
        visibility=CaseVisibility.CASE_SHARED,
    )
    assert theory.ok, theory.error
    npc = next(item for item in world_engine.get_npcs(instance.id) if item.key == "mechanic")
    suspect = world_engine.mark_suspect(
        instance.id,
        case_id=case_id,
        actor_id=alice,
        subject_type=SubjectType.NPC,
        subject_id=str(npc.id),
        reason="У него был доступ к оборудованию.",
    )
    assert suspect.ok, suspect.error

    closed = world_engine.close_case(instance.id, case_id=case_id, actor_id=alice)
    assert closed.ok, closed.error
    assert closed.payload["status"] == "CLOSED"
    assert world_engine.get_case(instance.id, case_id, viewer_id=bob).status == "CLOSED"
    assert world_engine.get_events(instance.id)[-1].type is EventType.CASE_CLOSED
    with uow_factory() as uow:
        assert len(uow.cases.list_evidence(instance.id, case_id)) == 3


def test_case_state_survives_subprocess_restart(
    world_engine: WorldEngine,
    db_url: str,
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    alice = create_character(world_engine, instance.id, "alice")
    case_id = case_id_for(world_engine, instance.id, alice)
    note = world_engine.add_case_note(
        instance.id,
        case_id=case_id,
        author_id=alice,
        text="Persisted note",
        visibility=CaseNoteVisibility.CASE_SHARED,
    )
    question = world_engine.add_case_question(
        instance.id, case_id=case_id, added_by=alice, text="Persisted question?"
    )
    assert note.ok and question.ok

    repo_root = Path(__file__).resolve().parents[2]
    script = """
import json
import os
from world_error.domain.shared.kernel import WorldInstanceId
from world_error.infrastructure.db.engine import create_db_engine, create_session_factory
from world_error.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
engine = create_db_engine(os.environ["WORLD_ERROR_DB_URL"])
try:
    factory = create_session_factory(engine)
    with SqlAlchemyUnitOfWork(factory) as uow:
        instance_id = WorldInstanceId(os.environ["CASE_TEST_INSTANCE_ID"])
        case = uow.cases.get_by_key(instance_id, "station_signal")
        notes = uow.cases.list_notes(instance_id, case.id)
        questions = uow.cases.list_questions(instance_id, case.id)
        print(json.dumps({
            "status": case.status.value,
            "notes": [note.text for note in notes],
            "questions": [question.text for question in questions],
        }))
finally:
    engine.dispose()
"""
    environment = {
        **os.environ,
        "WORLD_ERROR_DB_URL": db_url,
        "CASE_TEST_INSTANCE_ID": str(instance.id),
        "PYTHONPATH": str(repo_root / "src"),
        "PYTHONIOENCODING": "utf-8",
    }
    restarted = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert restarted.returncode == 0, restarted.stderr
    persisted = json.loads(restarted.stdout)
    assert persisted == {
        "status": "OPEN",
        "notes": ["Persisted note"],
        "questions": ["Persisted question?"],
    }


def test_case_action_event_id_is_idempotent(
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    catalog,
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    actor = create_character(world_engine, instance.id, "alice")
    case_id = case_id_for(world_engine, instance.id, actor)
    fixed_event_id = EventId("ev_case_idempotency")
    engine = WorldEngine(
        uow_factory=uow_factory,
        catalog=catalog,
        new_event_id_factory=lambda: fixed_event_id,
    )

    first = engine.add_case_note(
        instance.id, case_id=case_id, author_id=actor, text="Exactly once"
    )
    retried = engine.add_case_note(
        instance.id, case_id=case_id, author_id=actor, text="Must not duplicate"
    )

    assert first.ok, first.error
    assert first.event_ids == (fixed_event_id,)
    assert not retried.ok
    assert retried.error is not None and retried.error.code is ErrorCode.ALREADY_PROCESSED
    assert [item.text for item in engine.get_case_notes(instance.id, case_id, viewer_id=actor)] == [
        "Exactly once"
    ]
    assert sum(event.id == fixed_event_id for event in engine.get_events(instance.id)) == 1


def test_dead_character_remains_evidence_author_but_cannot_add_new_case_actions(
    world_engine: WorldEngine,
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1001, seed=42)
    author = create_character(world_engine, instance.id, "alice")
    witness = create_character(world_engine, instance.id, "bob")
    case_id = case_id_for(world_engine, instance.id, author)
    learn_information(world_engine, instance.id, author, "damaged_radio")
    information = world_engine.get_information(instance.id, "damaged_radio")
    linked = world_engine.link_evidence(
        instance.id, case_id=case_id, actor_id=author, information_id=information.id
    )
    assert linked.ok, linked.error
    link_id = CaseEvidenceLinkId(linked.payload["evidence_link_id"])

    cause_event_id = world_engine.get_events(instance.id)[-1].id
    death = world_engine.die_character(instance.id, author, cause_event_id=cause_event_id)
    assert death.ok, death.error
    evidence = world_engine.get_case_evidence(instance.id, case_id, viewer_id=witness)
    authored = next(item for item in evidence if item.evidence_link_id == str(link_id))
    assert authored.added_by == str(author)

    rejected = world_engine.add_case_note(
        instance.id, case_id=case_id, author_id=author, text="A new action after death"
    )
    assert not rejected.ok
    assert rejected.error is not None and rejected.error.code is ErrorCode.NOT_ALLOWED
