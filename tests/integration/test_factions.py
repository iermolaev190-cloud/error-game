"""Integration: faction isolation, relationships, status, and public projection."""

from __future__ import annotations

from dataclasses import fields
import subprocess
from typing import Callable

import pytest
from sqlalchemy import insert, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine

from world_error.application.services.world_engine import WorldEngine
from world_error.domain.factions.faction import FactionStatus
from world_error.domain.knowledge.knowledge import (
    ClaimType,
    Knowledge,
    KnowledgeConfidence,
    KnowledgeSource,
    SubjectType,
)
from world_error.domain.relationships.relationship import (
    MembershipLevel,
    RelationshipDirection,
    RelationshipKind,
    RelationshipVisibility,
    StandingLevel,
    SubjectRef,
)
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    EventId,
    FactionId,
    InformationId,
    KnowledgeId,
    LocationKey,
    NpcId,
    WorldInstanceId,
)
from world_error.infrastructure.db.tables import faction_locations


def _factions_by_key(world_engine: WorldEngine, instance_id) -> dict:
    return {faction.key: faction for faction in world_engine.get_factions(instance_id)}


def _faction_ref(faction_id: FactionId) -> SubjectRef:
    return SubjectRef(type=SubjectType.FACTION, id=str(faction_id))


def _cli_value(output: str, key: str) -> str:
    return next(line.split("=", 1)[1] for line in output.splitlines() if line.startswith(f"{key}="))


def _faction_ids(output: str) -> dict[str, str]:
    return {
        parts[2]: parts[1]
        for line in output.splitlines()
        if line.startswith("FACTION ")
        for parts in (line.split(),)
    }


def test_faction_lookup_is_instance_scoped(world_engine: WorldEngine) -> None:
    instance_a = world_engine.create_instance(telegram_chat_id=-1001, seed=1)
    instance_b = world_engine.create_instance(telegram_chat_id=-1002, seed=2)
    faction_a = _factions_by_key(world_engine, instance_a.id)["expedition"]

    with pytest.raises(DomainError) as exc_info:
        world_engine.get_faction(instance_b.id, faction_a.id)

    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert {faction.key for faction in world_engine.get_factions(instance_b.id)} == {
        "council",
        "expedition",
        "union",
    }


def test_faction_status_change_is_event_backed_and_rejects_unknown_status(
    world_engine: WorldEngine,
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1003, seed=3)
    faction = _factions_by_key(world_engine, instance.id)["council"]

    changed = world_engine.change_faction_status(
        instance.id, faction_id=faction.id, to_status=FactionStatus.CONFLICT
    )
    assert changed.ok is True
    assert world_engine.get_faction(instance.id, faction.id).status is FactionStatus.CONFLICT
    assert world_engine.get_events(instance.id)[-1].type.value == "FACTION_STATUS_CHANGED"

    invalid = world_engine.change_faction_status(
        instance.id, faction_id=faction.id, to_status="DISSOLVED"
    )
    assert invalid.ok is False
    assert invalid.error is not None and invalid.error.code is ErrorCode.INVALID_ACTION


def test_standing_is_asymmetric_and_membership_is_independent(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1004, seed=4)
    factions = _factions_by_key(world_engine, instance.id)
    expedition = _faction_ref(factions["expedition"].id)
    union = _faction_ref(factions["union"].id)
    character_result = world_engine.create_character(instance.id, player_id="worker", name="Worker")
    character = SubjectRef(
        type=SubjectType.CHARACTER,
        id=character_result.payload["character_id"],
    )

    standing = world_engine.change_relationship(
        instance.id,
        holder=expedition,
        subject=union,
        kind=RelationshipKind.STANDING,
        direction=RelationshipDirection.INCREASE,
    )
    membership = world_engine.change_relationship(
        instance.id,
        holder=expedition,
        subject=character,
        kind=RelationshipKind.MEMBERSHIP,
        direction=RelationshipDirection.INCREASE,
    )
    trust = world_engine.change_relationship(
        instance.id,
        holder=expedition,
        subject=character,
        kind=RelationshipKind.TRUST,
        direction=RelationshipDirection.INCREASE,
    )

    assert standing.ok and membership.ok and trust.ok
    standing_record = world_engine.get_relationship(
        instance.id, holder=expedition, subject=union, kind=RelationshipKind.STANDING
    )
    assert standing_record is not None and standing_record.level is StandingLevel.COMPETITIVE
    assert world_engine.get_relationship(
        instance.id, holder=union, subject=expedition, kind=RelationshipKind.STANDING
    ) is None
    membership_record = world_engine.get_relationship(
        instance.id, holder=expedition, subject=character, kind=RelationshipKind.MEMBERSHIP
    )
    assert membership_record is not None and membership_record.level is MembershipLevel.SYMPATHISER
    assert world_engine.get_relationship(
        instance.id, holder=expedition, subject=character, kind=RelationshipKind.TRUST
    ) is not None

    npc = next(iter(world_engine.get_npcs(instance.id)))
    invalid_membership = world_engine.change_relationship(
        instance.id,
        holder=expedition,
        subject=SubjectRef(type=SubjectType.NPC, id=str(npc.id)),
        kind=RelationshipKind.MEMBERSHIP,
        direction=RelationshipDirection.INCREASE,
    )
    assert invalid_membership.ok is False
    assert invalid_membership.error is not None
    assert invalid_membership.error.code is ErrorCode.INVALID_ACTION


def test_faction_relation_visibility_is_filtered(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1005, seed=5)
    factions = _factions_by_key(world_engine, instance.id)
    expedition = factions["expedition"]
    union = factions["union"]

    secret = world_engine.change_relationship(
        instance.id,
        holder=_faction_ref(expedition.id),
        subject=_faction_ref(union.id),
        kind=RelationshipKind.STANDING,
        direction=RelationshipDirection.INCREASE,
        visibility=RelationshipVisibility.SECRET,
    )
    assert secret.ok is True
    assert secret.event_ids
    assert world_engine.get_events(instance.id)[-1].payload["visibility"] == "SECRET"
    assert world_engine.get_faction_relations(instance.id, expedition.id, only_public=True) == []
    hidden = world_engine.get_faction_relations(instance.id, expedition.id, only_public=False)
    assert len(hidden) == 1 and hidden[0].visibility is RelationshipVisibility.SECRET

    public = world_engine.change_relationship(
        instance.id,
        holder=_faction_ref(factions["council"].id),
        subject=_faction_ref(expedition.id),
        kind=RelationshipKind.STANDING,
        direction=RelationshipDirection.INCREASE,
    )
    assert public.ok is True
    relations = world_engine.get_faction_relations(instance.id, factions["council"].id)
    assert len(relations) == 1 and relations[0].visibility is RelationshipVisibility.PUBLIC


def test_faction_knowledge_has_no_application_write_path(world_engine: WorldEngine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1006, seed=6)
    faction = _factions_by_key(world_engine, instance.id)["expedition"]

    result = world_engine.npc_learn(
        instance.id,
        npc_id=NpcId(str(faction.id)),
        information_key="damaged_radio",
    )

    assert result.ok is False
    assert result.error is not None and result.error.code is ErrorCode.NOT_FOUND
    with uow_factory() as uow:
        assert uow.knowledge.list_for_subject(
            instance.id, SubjectType.FACTION, str(faction.id)
        ) == []


def test_public_queries_do_not_expose_faction_knowledge(
    world_engine: WorldEngine, uow_factory, cli, db_url: str
) -> None:
    from world_error.application.queries.faction_view import FactionView
    from world_error.application.queries.location_view import LocationView

    instance = world_engine.create_instance(telegram_chat_id=-1013, seed=13)
    faction = _factions_by_key(world_engine, instance.id)["expedition"]
    character_result = world_engine.create_character(instance.id, player_id="viewer", name="Viewer")
    character_id = CharacterId(character_result.payload["character_id"])
    claim = "FACTION_PRIVATE_KNOWLEDGE_SENTINEL"

    with uow_factory() as uow:
        information = uow.information.get_by_key(instance.id, "damaged_radio")
        uow.knowledge.add(
            Knowledge.record(
                id=KnowledgeId("kn_faction_private"),
                world_instance_id=instance.id,
                subject_type=SubjectType.FACTION,
                subject_id=str(faction.id),
                information_id=InformationId(str(information.id)),
                claim=claim,
                claim_type=ClaimType.CLAIM,
                source=KnowledgeSource.OBSERVATION,
                source_ref=str(faction.id),
                confidence=KnowledgeConfidence.LIKELY,
                acquired_at=instance.created_at,
            )
        )
        uow.commit()

    location_view = world_engine.view_location(
        instance.id,
        observer_id=character_id,
        location_key=LocationKey("base"),
    )
    faction_views = world_engine.view_factions(instance.id)
    assert "knowledge" not in {field.name for field in fields(LocationView)}
    assert "knowledge" not in {field.name for field in fields(FactionView)}
    assert claim not in repr(location_view)
    assert claim not in repr(faction_views)

    shown_location = cli(
        db_url,
        "show-location",
        "--world-id", str(instance.id),
        "--character-id", str(character_id),
        "--location", "base",
    )
    shown_character = cli(
        db_url, "show-character", "--world-id", str(instance.id), "--character-id", str(character_id)
    )
    shown_npc = cli(
        db_url,
        "show-npc",
        "--world-id", str(instance.id),
        "--npc-id", str(next(iter(world_engine.get_npcs(instance.id))).id),
    )
    shown_factions = cli(db_url, "show-factions", "--world-id", str(instance.id))
    for result in (shown_location, shown_character, shown_npc, shown_factions):
        assert result.returncode == 0, result.stderr
        assert claim not in result.stdout


def test_faction_locations_have_composite_instance_foreign_keys(
    world_engine: WorldEngine, engine: Engine
) -> None:
    instance_a = world_engine.create_instance(telegram_chat_id=-1007, seed=7)
    instance_b = world_engine.create_instance(telegram_chat_id=-1008, seed=8)
    faction_b = _factions_by_key(world_engine, instance_b.id)["expedition"]

    foreign_keys = inspect(engine).get_foreign_keys("faction_locations")
    foreign_key_pairs = {tuple(foreign_key["constrained_columns"]) for foreign_key in foreign_keys}
    assert ("world_instance_id", "faction_id") in foreign_key_pairs
    assert ("world_instance_id", "location_key") in foreign_key_pairs

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                insert(faction_locations).values(
                    world_instance_id=str(instance_a.id),
                    faction_id=str(faction_b.id),
                    location_key="base",
                )
            )


def test_faction_status_and_relationship_events_are_idempotent(
    world_engine: WorldEngine, uow_factory: Callable, catalog
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1009, seed=9)
    faction = _factions_by_key(world_engine, instance.id)["council"]
    factions = _factions_by_key(world_engine, instance.id)
    status_engine = WorldEngine(
        uow_factory=uow_factory,
        catalog=catalog,
        new_event_id_factory=lambda: EventId("ev_faction_status_once"),
    )
    status_first = status_engine.change_faction_status(
        instance.id, faction_id=faction.id, to_status=FactionStatus.CONFLICT
    )
    status_retry = status_engine.change_faction_status(
        instance.id, faction_id=faction.id, to_status=FactionStatus.DIVIDED
    )
    assert status_first.ok is True
    assert status_retry.ok is False
    assert status_retry.error is not None
    assert status_retry.error.code is ErrorCode.ALREADY_PROCESSED
    assert world_engine.get_faction(instance.id, faction.id).status is FactionStatus.CONFLICT

    relationship_engine = WorldEngine(
        uow_factory=uow_factory,
        catalog=catalog,
        new_event_id_factory=lambda: EventId("ev_faction_relation_once"),
    )
    holder = _faction_ref(factions["expedition"].id)
    subject = _faction_ref(factions["union"].id)
    first = relationship_engine.change_relationship(
        instance.id,
        holder=holder,
        subject=subject,
        kind=RelationshipKind.STANDING,
        direction=RelationshipDirection.INCREASE,
    )
    retry = relationship_engine.change_relationship(
        instance.id,
        holder=holder,
        subject=subject,
        kind=RelationshipKind.STANDING,
        direction=RelationshipDirection.INCREASE,
    )
    assert first.ok is True
    assert retry.ok is False
    assert retry.error is not None and retry.error.code is ErrorCode.ALREADY_PROCESSED
    relationship = world_engine.get_relationship(
        instance.id, holder=holder, subject=subject, kind=RelationshipKind.STANDING
    )
    assert relationship is not None and relationship.level is StandingLevel.COMPETITIVE


def test_factions_relations_and_visibility_survive_subprocess_restarts(
    cli: Callable[..., subprocess.CompletedProcess[str]], db_url: str, world_engine: WorldEngine
) -> None:
    created = cli(db_url, "create-world", "--chat-id", "-1010", "--seed", "10")
    assert created.returncode == 0, created.stderr
    instance_id = _cli_value(created.stdout, "instance_id")
    listed = cli(db_url, "show-factions", "--world-id", instance_id)
    assert listed.returncode == 0, listed.stderr
    faction_ids = _faction_ids(listed.stdout)
    expedition_id = faction_ids["expedition"]
    union_id = faction_ids["union"]

    character_result = cli(
        db_url,
        "create-character",
        "--world-id",
        instance_id,
        "--player-id",
        "worker",
        "--name",
        "Worker",
    )
    assert character_result.returncode == 0, character_result.stderr
    character_id = _cli_value(character_result.stdout, "character_id")

    standing_first = cli(
        db_url,
        "relationship-change",
        "--world-id", instance_id,
        "--holder-type", "FACTION",
        "--holder-id", expedition_id,
        "--subject-type", "FACTION",
        "--subject-id", union_id,
        "--kind", "STANDING",
        "--direction", "INCREASE",
        "--visibility", "SECRET",
    )
    standing_retry = cli(
        db_url,
        "relationship-change",
        "--world-id", instance_id,
        "--holder-type", "FACTION",
        "--holder-id", expedition_id,
        "--subject-type", "FACTION",
        "--subject-id", union_id,
        "--kind", "STANDING",
        "--direction", "INCREASE",
    )
    assert standing_first.returncode == 0, standing_first.stderr
    assert standing_retry.returncode == 0, standing_retry.stderr
    assert "from=COMPETITIVE" in standing_retry.stdout
    assert "visibility=SECRET" in standing_retry.stdout

    membership_first = cli(
        db_url,
        "relationship-change",
        "--world-id", instance_id,
        "--holder-type", "FACTION",
        "--holder-id", expedition_id,
        "--subject-type", "CHARACTER",
        "--subject-id", character_id,
        "--kind", "MEMBERSHIP",
        "--direction", "INCREASE",
        "--visibility", "SECRET",
    )
    membership_retry = cli(
        db_url,
        "relationship-change",
        "--world-id", instance_id,
        "--holder-type", "FACTION",
        "--holder-id", expedition_id,
        "--subject-type", "CHARACTER",
        "--subject-id", character_id,
        "--kind", "MEMBERSHIP",
        "--direction", "INCREASE",
    )
    assert membership_first.returncode == 0, membership_first.stderr
    assert membership_retry.returncode == 0, membership_retry.stderr
    assert "from=SYMPATHISER" in membership_retry.stdout
    assert "to=MEMBER" in membership_retry.stdout
    assert "visibility=SECRET" in membership_retry.stdout

    instance = world_engine.get_instance(WorldInstanceId(instance_id))
    status = world_engine.change_faction_status(
        instance.id,
        faction_id=FactionId(expedition_id),
        to_status=FactionStatus.CONFLICT,
    )
    assert status.ok is True, status.error
    shown_again = cli(db_url, "show-factions", "--world-id", instance_id)
    assert shown_again.returncode == 0, shown_again.stderr
    assert "CONFLICT" in shown_again.stdout
    assert "hidden_goal" not in shown_again.stdout
    assert "Скрывать, что пропавшего исследователя" not in shown_again.stdout


def test_f1_standing_change_does_not_change_inverse(world_engine: WorldEngine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-1014, seed=14)
    factions = _factions_by_key(world_engine, instance.id)
    expedition = _faction_ref(factions["expedition"].id)
    union = _faction_ref(factions["union"].id)

    changed = world_engine.change_relationship(
        instance.id,
        holder=expedition,
        subject=union,
        kind=RelationshipKind.STANDING,
        direction=RelationshipDirection.INCREASE,
    )

    assert changed.ok is True
    forward = world_engine.get_relationship(
        instance.id, holder=expedition, subject=union, kind=RelationshipKind.STANDING
    )
    inverse = world_engine.get_relationship(
        instance.id, holder=union, subject=expedition, kind=RelationshipKind.STANDING
    )
    assert forward is not None and forward.level is StandingLevel.COMPETITIVE
    assert inverse is None


def test_f2_hidden_goal_is_absent_from_public_view_and_cli(
    cli, db_url: str, world_engine: WorldEngine
) -> None:
    from world_error.application.queries.faction_view import FactionView
    from world_error.domain.factions.faction import Faction

    field_names = {field.name for field in fields(Faction)}
    view_field_names = {field.name for field in fields(FactionView)}

    assert "hidden_goal" not in field_names
    assert "knowledge" not in view_field_names
    assert "hidden_goal" not in view_field_names

    instance = world_engine.create_instance(telegram_chat_id=-1015, seed=15)
    shown = cli(db_url, "show-factions", "--world-id", str(instance.id))
    assert shown.returncode == 0, shown.stderr
    assert "hidden_goal" not in shown.stdout
    assert "Скрывать, что пропавшего исследователя" not in shown.stdout