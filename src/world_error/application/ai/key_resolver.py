"""Resolve player-facing entity keys to IDs inside one WORLD INSTANCE."""

from __future__ import annotations

import re

from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.characters.character import CharacterActivity, CharacterLifecycle
from world_error.domain.items.item import ItemOwnerType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.npcs.npc import NpcStatus
from world_error.domain.shared.kernel import (
    CharacterId,
    ItemId,
    LocationKey,
    NpcId,
    WorldInstanceId,
)


def _name_key(value: str) -> str:
    return re.sub(r"[^\w]+", "_", value.casefold(), flags=re.UNICODE).strip("_")


class InstanceKeyResolver:
    """Resolve action targets using only repositories scoped by instance ID."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def resolve_location_item(
        self,
        world_instance_id: WorldInstanceId,
        location_key: LocationKey,
        item_key: str,
    ) -> ItemId | None:
        with self._uow_factory() as uow:
            item = next(
                (
                    item
                    for item in uow.items.list_at_location(world_instance_id, location_key)
                    if item.key.casefold() == item_key.casefold()
                    and item.owner_type is ItemOwnerType.LOCATION
                ),
                None,
            )
        return None if item is None else item.id

    def resolve_inventory_item(
        self,
        world_instance_id: WorldInstanceId,
        character_id: CharacterId,
        item_key: str,
    ) -> ItemId | None:
        with self._uow_factory() as uow:
            item = next(
                (
                    item
                    for item in uow.items.list_by_owner(
                        world_instance_id, ItemOwnerType.CHARACTER, str(character_id)
                    )
                    if item.key.casefold() == item_key.casefold()
                ),
                None,
            )
        return None if item is None else item.id

    def resolve_known_information(
        self,
        world_instance_id: WorldInstanceId,
        character_id: CharacterId,
        information_key: str,
    ) -> str | None:
        normalized_key = information_key.casefold()
        with self._uow_factory() as uow:
            information_key_found = next(
                (
                    information.key
                    for knowledge in uow.knowledge.list_for_subject(
                        world_instance_id, SubjectType.CHARACTER, str(character_id)
                    )
                    if (
                        information := uow.information.get(
                            world_instance_id, knowledge.information_id
                        )
                    ).key.casefold()
                    == normalized_key
                ),
                None,
            )
        return information_key_found

    def resolve_npc(
        self,
        world_instance_id: WorldInstanceId,
        location_key: LocationKey,
        npc_key: str,
    ) -> NpcId | None:
        with self._uow_factory() as uow:
            npc = next(
                (
                    npc
                    for npc in uow.npcs.list_in_location(world_instance_id, location_key)
                    if npc.key.casefold() == npc_key.casefold()
                    and npc.status is NpcStatus.ACTIVE
                ),
                None,
            )
        return None if npc is None else npc.id

    def resolve_npc_in_instance(
        self,
        world_instance_id: WorldInstanceId,
        npc_key: str,
    ) -> NpcId | None:
        normalized_key = npc_key.casefold()
        with self._uow_factory() as uow:
            npc = next(
                (
                    npc
                    for npc in uow.npcs.list_for_instance(world_instance_id)
                    if npc.key.casefold() == normalized_key
                    and npc.status is NpcStatus.ACTIVE
                ),
                None,
            )
        return None if npc is None else npc.id

    def resolve_character(
        self,
        world_instance_id: WorldInstanceId,
        location_key: LocationKey,
        character_key: str,
    ) -> CharacterId | None:
        normalized_key = character_key.casefold()
        with self._uow_factory() as uow:
            character = next(
                (
                    character
                    for character in uow.characters.list_by_location(
                        world_instance_id, location_key
                    )
                    if character.lifecycle is CharacterLifecycle.ALIVE
                    and character.activity is CharacterActivity.ACTIVE
                    and (
                        str(character.id).casefold() == normalized_key
                        or _name_key(character.name) == normalized_key
                    )
                ),
                None,
            )
        return None if character is None else character.id
