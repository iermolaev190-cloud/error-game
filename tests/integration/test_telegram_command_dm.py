import asyncio

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.domain.items.item import ItemOwnerType
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.shared.kernel import CharacterId, LocationKey
from world_error.interfaces.telegram.adapter import (
    TelegramAdapter,
    TelegramIncomingMessage,
)
from world_error.interfaces.telegram.resolver import GroupInstanceResolver


class MockTelegramClient:
    async def send_message(self, chat_id: int, text: str) -> None:
        pass

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "private", "title": None})()


def send_dm(adapter: TelegramAdapter, user_id: int, text: str) -> str:
    return asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=user_id,
                chat_type="private",
                telegram_user_id=user_id,
                text=text,
            )
        )
    )


def test_dm_slash_commands_cover_actions_queries_and_talk(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9940, seed=40)
    created = world_engine.create_character(
        instance.id,
        player_id="9940",
        name="DM Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    resolver.record_last_group_chat(9940, -9940)
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=resolver,
    )

    assert "location=" in send_dm(adapter, 9940, "/look")
    assert "Смотритель" in send_dm(adapter, 9940, "/npcs")
    help_text = send_dm(adapter, 9940, "/help")
    assert "/inventory" in help_text and "/talk <npc>" in help_text
    assert "character=DM Player" in send_dm(adapter, 9940, "/character")
    assert "inventory" in send_dm(adapter, 9940, "/inventory")
    assert "knowledge" in send_dm(adapter, 9940, "/knowledge")

    taken = send_dm(adapter, 9940, "/take medkit")
    assert "action=TAKE" in taken and "ok=true" in taken
    dropped = send_dm(adapter, 9940, "/drop medkit")
    assert "action=DROP" in dropped and "ok=true" in dropped
    dialogue = send_dm(adapter, 9940, "/talk caretaker")
    assert "action=TALK_TO_NPC" in dialogue and "reply=" in dialogue
    fallback_dialogue = send_dm(adapter, 9940, "talk to caretaker")
    assert "action=TALK_TO_NPC" in fallback_dialogue and "reply=" in fallback_dialogue

    moved = send_dm(adapter, 9940, "/move forest")
    assert "action=MOVE" in moved and "ok=true" in moved
    moved = send_dm(adapter, 9940, "/move old_station")
    assert "action=MOVE" in moved and "ok=true" in moved
    inspected = send_dm(adapter, 9940, "/inspect damaged_radio")
    assert "action=INSPECT" in inspected and "claim=" in inspected
    assert world_engine.get_character(instance.id, character_id).location_key == LocationKey(
        "old_station"
    )


def test_dm_give_share_and_trade_commands(world_engine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9941, seed=41)
    initiator = world_engine.create_character(
        instance.id,
        player_id="9941",
        name="DM Initiator",
        location_key=LocationKey("base"),
    )
    counterparty = world_engine.create_character(
        instance.id,
        player_id="9942",
        name="DM Counterparty",
        location_key=LocationKey("base"),
    )
    assert initiator.ok and counterparty.ok
    initiator_id = CharacterId(initiator.payload["character_id"])
    counterparty_id = CharacterId(counterparty.payload["character_id"])
    with uow_factory() as uow:
        items = {
            item.key: item
            for item in uow.items.list_at_location(instance.id, LocationKey("base"))
        }
    assert world_engine.take_item(
        instance.id, character_id=initiator_id, item_id=items["medkit"].id
    ).ok
    assert world_engine.take_item(
        instance.id, character_id=counterparty_id, item_id=items["credits"].id
    ).ok
    assert world_engine.inspect_information(
        instance.id, character_id=initiator_id, target_key="dispatch_log"
    ).ok
    resolver = GroupInstanceResolver(world_engine, uow_factory)
    resolver.record_last_group_chat(9941, -9941)
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=resolver,
    )

    traded = send_dm(adapter, 9941, "/trade DM_Counterparty medkit credits")
    assert "action=TRADE" in traded and "ok=true" in traded
    shared = send_dm(adapter, 9941, "/share DM_Counterparty dispatch_log")
    assert "action=SHARE" in shared and "ok=true" in shared
    given = send_dm(adapter, 9941, "/give DM_Counterparty credits")
    assert "action=GIVE" in given and "ok=true" in given

    with uow_factory() as uow:
        information_id = uow.information.get_by_key(instance.id, "dispatch_log").id
        initiator_knowledge = uow.knowledge.find(
            instance.id, SubjectType.CHARACTER, str(initiator_id), information_id
        )
        counterparty_knowledge = uow.knowledge.find(
            instance.id, SubjectType.CHARACTER, str(counterparty_id), information_id
        )
        inventory = uow.items.list_by_owner(
            instance.id, ItemOwnerType.CHARACTER, str(counterparty_id)
        )
    assert initiator_knowledge is not None and counterparty_knowledge is not None
    assert counterparty_knowledge.claim == initiator_knowledge.claim
    assert {item.key for item in inventory} == {"credits", "medkit"}
    rejected = send_dm(adapter, 9941, "/give caretaker medkit")
    assert "ok=false" in rejected and "character" in rejected
