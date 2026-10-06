"""Репозиторий персонажей."""

from __future__ import annotations

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from world_error.domain.characters.character import (
    Character,
    CharacterActivity,
    CharacterLifecycle,
)
from world_error.domain.shared.kernel import CharacterId, DomainError, ErrorCode, WorldInstanceId
from world_error.domain.world.instance import InstanceLifecycle
from world_error.infrastructure.db.repositories._mapping import (
    character_from_row,
    character_row,
)
from world_error.infrastructure.db.tables import characters, world_instances


class SqlCharacterRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, character: Character) -> None:
        self._session.execute(insert(characters).values(**character_row(character)))

    def get(self, world_instance_id: WorldInstanceId, character_id: CharacterId) -> Character:
        row = (
            self._session.execute(
                select(characters).where(
                    characters.c.world_instance_id == str(world_instance_id),
                    characters.c.id == str(character_id),
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DomainError(ErrorCode.NOT_FOUND, f"character not found: {character_id}")
        return character_from_row(dict(row))

    def find_alive_by_player(
        self, world_instance_id: WorldInstanceId, player_id: str
    ) -> Character | None:
        row = (
            self._session.execute(
                select(characters).where(
                    characters.c.world_instance_id == str(world_instance_id),
                    characters.c.player_id == player_id,
                    characters.c.lifecycle == CharacterLifecycle.ALIVE.value,
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else character_from_row(dict(row))

    def find_by_instance_and_player(
        self, world_instance_id: WorldInstanceId, player_id: str
    ) -> Character | None:
        row = (
            self._session.execute(
                select(characters)
                .where(
                    characters.c.world_instance_id == str(world_instance_id),
                    characters.c.player_id == player_id,
                    characters.c.lifecycle == CharacterLifecycle.ALIVE.value,
                    characters.c.activity == CharacterActivity.ACTIVE.value,
                )
                .order_by(characters.c.created_at.desc(), characters.c.id)
            )
            .mappings()
            .first()
        )
        return None if row is None else character_from_row(dict(row))

    def list_active_by_player(self, player_id: str) -> list[Character]:
        rows = self._session.execute(
            select(characters)
            .select_from(
                characters.join(
                    world_instances,
                    characters.c.world_instance_id == world_instances.c.id,
                )
            )
            .where(
                characters.c.player_id == player_id,
                characters.c.lifecycle == CharacterLifecycle.ALIVE.value,
                characters.c.activity == CharacterActivity.ACTIVE.value,
                world_instances.c.lifecycle == InstanceLifecycle.ACTIVE.value,
            )
            .distinct()
            .order_by(characters.c.world_instance_id, characters.c.id)
        ).all()
        return [character_from_row(dict(row._mapping)) for row in rows]

    def list_by_location(
        self, world_instance_id: WorldInstanceId, location_key: LocationKey
    ) -> list[Character]:
        stmt = (
            select(characters)
            .where(
                characters.c.world_instance_id == str(world_instance_id),
                characters.c.location_key == str(location_key),
            )
            .order_by(characters.c.name, characters.c.id)
        )
        return [character_from_row(dict(row)) for row in self._session.execute(stmt).mappings().all()]

    def save(self, character: Character) -> None:
        result = self._session.execute(
            update(characters)
            .where(
                characters.c.world_instance_id == str(character.world_instance_id),
                characters.c.id == str(character.id),
            )
            .values(**character_row(character))
        )
        if result.rowcount == 0:
            raise DomainError(ErrorCode.NOT_FOUND, f"character not found: {character.id}")
