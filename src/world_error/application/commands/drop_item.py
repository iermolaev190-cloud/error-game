"""Drop a character-owned item in the character's current location."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._item_transfer import ItemTransferWorkspace
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.content.catalog import ContentCatalog
from world_error.domain.events.event import Event, EventType
from world_error.domain.items.item import ItemOwnerType
from world_error.domain.shared.kernel import (
    CharacterId,
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    ItemId,
    WorldInstanceId,
    new_event_id,
    new_item_id,
)


@dataclass(frozen=True, slots=True)
class DropItemCommand:
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    item_id: ItemId
    quantity: int | None = None
    cause: str = "drop_item"


class DropItemHandler:
    ACTION = "DROP"

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        catalog: ContentCatalog,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
        new_item_id_factory: Callable[[], ItemId] = new_item_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._catalog = catalog
        self._new_event_id = new_event_id_factory
        self._new_item_id = new_item_id_factory

    def handle(self, command: DropItemCommand) -> ActionResult:
        try:
            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                character = uow.characters.get(instance.id, command.character_id)
                character.ensure_can_act()
                item = uow.items.get(instance.id, command.item_id)
                if (
                    item.owner_type is not ItemOwnerType.CHARACTER
                    or item.owner_id != str(character.id)
                ):
                    raise DomainError(ErrorCode.NOT_ALLOWED, "character does not own this item")

                location_items = uow.items.list_at_location(instance.id, character.location_key)
                now = self._clock.now()
                workspace = ItemTransferWorkspace(
                    catalog=self._catalog,
                    now=now,
                    new_item_id=self._new_item_id,
                    existing_items=(item, *location_items),
                )
                receipt = workspace.transfer(
                    item_id=item.id,
                    quantity=item.quantity if command.quantity is None else command.quantity,
                    owner_type=ItemOwnerType.LOCATION,
                    owner_id=None,
                    location_key=character.location_key,
                )
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.ITEM_DROPPED,
                    created_at=now,
                    executed_at=now,
                    actor=str(character.id),
                    target=str(item.id),
                    cause=command.cause,
                    payload={
                        **workspace.event_payload(),
                        "character_id": str(character.id),
                        "location_key": str(character.location_key),
                    },
                    result="success",
                )
                workspace.persist(
                    uow=uow,
                    instance=instance,
                    expected_state_version=expected_version,
                    event=event,
                )

            return ActionResult.success(
                self.ACTION,
                event_ids=(event.id,),
                payload={
                    "item_id": str(item.id),
                    "destination_item_id": str(receipt.destination_item_id),
                    "quantity": receipt.quantity,
                    "merged_into_existing": receipt.merged_into_existing,
                    "location_key": str(character.location_key),
                    "world_tick": instance.state.world_tick,
                    "state_version": instance.state.state_version,
                },
            )
        except DomainError as exc:
            return ActionResult.failure(self.ACTION, exc)