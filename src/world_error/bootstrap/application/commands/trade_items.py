"""Direct co-located character trade, or a one-way give, in one event/UoW."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from world_error.application.action_result import ActionResult
from world_error.application.commands._item_transfer import ItemTransferWorkspace
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.characters.character import CharacterLifecycle
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
class TradeItemsCommand:
    world_instance_id: WorldInstanceId
    initiator_id: CharacterId
    counterparty_id: CharacterId
    offered_item_id: ItemId
    offered_quantity: int | None = None
    requested_item_id: ItemId | None = None
    requested_quantity: int | None = None
    cause: str = "trade_items"


class TradeItemsHandler:
    ACTION = "TRADE"

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

    def handle(self, command: TradeItemsCommand) -> ActionResult:
        action = self.ACTION if command.requested_item_id is not None else "GIVE"
        try:
            if command.requested_item_id is None and command.requested_quantity is not None:
                raise DomainError(ErrorCode.INVALID_ACTION, "requested quantity requires a requested item")

            with self._uow_factory() as uow:
                instance = uow.world_instances.get(command.world_instance_id)
                expected_version = instance.state.state_version
                event_id = self._new_event_id()
                if uow.events.has_event(instance.id, event_id):
                    raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event_id}")
                initiator = uow.characters.get(instance.id, command.initiator_id)
                initiator.ensure_can_act()
                counterparty = uow.characters.get(instance.id, command.counterparty_id)
                if initiator.id == counterparty.id:
                    raise DomainError(ErrorCode.INVALID_ACTION, "a character cannot trade with itself")
                if counterparty.lifecycle is not CharacterLifecycle.ALIVE:
                    raise DomainError(ErrorCode.NOT_ALLOWED, "counterparty is not alive")
                if initiator.location_key != counterparty.location_key:
                    raise DomainError(ErrorCode.NOT_ALLOWED, "characters are in different locations")

                offered_item = uow.items.get(instance.id, command.offered_item_id)
                if (
                    offered_item.owner_type is not ItemOwnerType.CHARACTER
                    or offered_item.owner_id != str(initiator.id)
                ):
                    raise DomainError(ErrorCode.NOT_ALLOWED, "initiator does not own offered item")

                requested_item = None
                if command.requested_item_id is not None:
                    requested_item = uow.items.get(instance.id, command.requested_item_id)
                    if (
                        requested_item.owner_type is not ItemOwnerType.CHARACTER
                        or requested_item.owner_id != str(counterparty.id)
                    ):
                        raise DomainError(ErrorCode.NOT_ALLOWED, "counterparty does not own requested item")

                existing_items = [
                    *uow.items.list_by_owner(
                        instance.id, ItemOwnerType.CHARACTER, str(initiator.id)
                    ),
                    *uow.items.list_by_owner(
                        instance.id, ItemOwnerType.CHARACTER, str(counterparty.id)
                    ),
                ]
                if requested_item is not None:
                    existing_items.append(requested_item)
                existing_items.append(offered_item)
                now = self._clock.now()
                workspace = ItemTransferWorkspace(
                    catalog=self._catalog,
                    now=now,
                    new_item_id=self._new_item_id,
                    existing_items=existing_items,
                )

                # Process the counterparty's leg first so a partial stack can
                # remain available as the initiator's merge destination.
                requested_receipt = None
                if requested_item is not None:
                    requested_receipt = workspace.transfer(
                        item_id=requested_item.id,
                        quantity=(
                            requested_item.quantity
                            if command.requested_quantity is None
                            else command.requested_quantity
                        ),
                        owner_type=ItemOwnerType.CHARACTER,
                        owner_id=str(initiator.id),
                        location_key=None,
                        excluded_target_ids=frozenset({offered_item.id}),
                    )

                offered_receipt = workspace.transfer(
                    item_id=offered_item.id,
                    quantity=(
                        offered_item.quantity
                        if command.offered_quantity is None
                        else command.offered_quantity
                    ),
                    owner_type=ItemOwnerType.CHARACTER,
                    owner_id=str(counterparty.id),
                    location_key=None,
                )
                event = Event(
                    id=event_id,
                    world_instance_id=instance.id,
                    type=EventType.ITEM_TRANSFERRED,
                    created_at=now,
                    executed_at=now,
                    actor=str(initiator.id),
                    target=str(counterparty.id),
                    cause=command.cause,
                    payload={
                        **workspace.event_payload(),
                        "initiator_character_id": str(initiator.id),
                        "counterparty_character_id": str(counterparty.id),
                        "location_key": str(initiator.location_key),
                    },
                    result="success",
                )
                workspace.persist(
                    uow=uow,
                    instance=instance,
                    expected_state_version=expected_version,
                    event=event,
                )

            payload: dict[str, object] = {
                "offered_item_id": str(offered_item.id),
                "offered_destination_item_id": str(offered_receipt.destination_item_id),
                "offered_quantity": offered_receipt.quantity,
                "offered_merged_into_existing": offered_receipt.merged_into_existing,
                "initiator_character_id": str(initiator.id),
                "counterparty_character_id": str(counterparty.id),
                "world_tick": instance.state.world_tick,
                "state_version": instance.state.state_version,
            }
            if requested_receipt is not None:
                payload.update(
                    {
                        "requested_item_id": str(requested_item.id),
                        "requested_destination_item_id": str(requested_receipt.destination_item_id),
                        "requested_quantity": requested_receipt.quantity,
                        "requested_merged_into_existing": requested_receipt.merged_into_existing,
                    }
                )
            return ActionResult.success(action, event_ids=(event.id,), payload=payload)
        except DomainError as exc:
            return ActionResult.failure(action, exc)