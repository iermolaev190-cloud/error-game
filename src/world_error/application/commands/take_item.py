"""Take an item currently placed in the actor's location."""

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
class TakeItemCommand:
    world_instance_id: WorldInstanceId
    character_id: CharacterId
    item_id: ItemId
    quantity: int | None = None
    cause: str = "take_item"


class TakeItemHandler:
    ACTION = "TAKE"

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

    def handle(self, command: TakeItemCommand) -> ActionResult:
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
                if item.owner_type not in (ItemOwnerType.LOCATION, ItemOwnerType.NONE):
                    raise DomainError(ErrorCode.NOT_ALLOWED, "item is not available in a location")
                if item.location_key != character.location_key:
                    raise DomainError(ErrorCode.NOT_ALLOWED, "item is not in the character's location")

                inventory = uow.items.list_by_owner(
                    instance.id, ItemOwnerType.CHARACTER, str(character.id)
                )
                now = self._clock.now()
                workspace = ItemTransferWorkspace(
                    catalog=self._catalog,
                    now=now,
                    new_item_id=self._new_item_id,
                    existing_items=(item, *inventory),
                )
                receipt = workspace.transfer(
                    item_id=item.id,
                    quantity=item.quantity if command.quantity is None else command.quantity,
                    owner_type=ItemOwnerType.CHARACTER,
                    owner_id=str(character.id),
                    location_key=None,
                )
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.ITEM_TAKEN,
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