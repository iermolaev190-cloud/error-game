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
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def get_chat(self, chat_id: int):
        return type("Chat", (), {"id": chat_id, "type": "private", "title": None})()


def send_group(
    adapter: TelegramAdapter,
    text: str,
    user_id: int = 9920,
    chat_id: int = -9920,
) -> str:
    return asyncio.run(
        adapter.handle_message(
            TelegramIncomingMessage(
                chat_id=chat_id,
                chat_type="group",
                telegram_user_id=user_id,
                text=text,
            )
        )
    )


def test_group_slash_commands_route_public_queries_and_actions(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9920, seed=20)
    created = world_engine.create_character(
        instance.id,
        player_id="9920",
        name="Group Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    client = MockTelegramClient()
    adapter = TelegramAdapter(
        telegram_client=client,
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    look = send_group(adapter, "/look")
    assert "location=" in look
    assert "npcs=" in look
    assert "items=" in look
    assert "exits=" in look
    assert "knowledge" not in look
    assert "inventory" not in look

    npcs = send_group(adapter, "/npcs")
    assert "Смотритель" in npcs

    moved = send_group(adapter, "/move forest")
    assert "action=MOVE" in moved
    assert world_engine.get_character(
        instance.id, CharacterId(created.payload["character_id"])
    ).location_key == LocationKey("forest")

    taken = send_group(adapter, "/take medkit")
    assert "action=TAKE" in taken
    assert "ok=true" in taken
    assert client.sent[-1] == (-9920, taken)
    dropped = send_group(adapter, "drop medkit")
    assert "action=DROP" in dropped and "ok=true" in dropped
    fallback_taken = send_group(adapter, "take medkit")
    assert "action=TAKE" in fallback_taken and "ok=true" in fallback_taken

    assert "action=MOVE" in send_group(adapter, "/move old_station")
    inspected = send_group(adapter, "/inspect damaged_radio")
    assert "Ссылка: https://example.com/archive-17" in inspected


def test_take_and_drop_failures_suggest_next_step(world_engine, uow_factory) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9925, seed=25)
    created = world_engine.create_character(
        instance.id,
        player_id="9925",
        name="Inventory Player",
        location_key=LocationKey("base"),
    )
    assert created.ok, created.error
    character_id = CharacterId(created.payload["character_id"])
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    assert "ok=true" in send_group(adapter, "/take medkit", user_id=9925, chat_id=-9925)
    already_owned = send_group(adapter, "/take medkit", user_id=9925, chat_id=-9925)
    assert "У тебя уже есть 'medkit'." in already_owned
    assert "Проверь /inventory в DM." in already_owned
    absent = send_group(adapter, "/take flashlight", user_id=9925, chat_id=-9925)
    assert "Здесь нет 'flashlight'." in absent
    assert "Проверь /look в локации." in absent
    drop_missing = send_group(adapter, "/drop flashlight", user_id=9925, chat_id=-9925)
    assert "У тебя нет 'flashlight' в инвентаре." in drop_missing
    assert "Проверь /inventory в DM." in drop_missing


def test_group_give_share_and_trade_commands(world_engine, uow_factory, catalog) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9921, seed=21)
    initiator = world_engine.create_character(
        instance.id,
        player_id="9921",
        name="Group Initiator",
        location_key=LocationKey("base"),
    )
    counterparty = world_engine.create_character(
        instance.id,
        player_id="9922",
        name="Group Counterparty",
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
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    no_item = send_group(
        adapter,
        "/give Group_Counterparty flashlight",
        user_id=9921,
        chat_id=-9921,
    )
    assert "У тебя нет 'flashlight' в инвентаре." in no_item
    no_knowledge = send_group(
        adapter,
        "/share Group_Counterparty damaged_radio",
        user_id=9921,
        chat_id=-9921,
    )
    assert "Ты не знаешь 'damaged_radio'" in no_knowledge
    no_requested_item = send_group(
        adapter,
        "/trade Group_Counterparty medkit flashlight",
        user_id=9921,
        chat_id=-9921,
    )
    assert "У 'group_counterparty' нет 'flashlight' в инвентаре." in no_requested_item

    events_before_npc_give = tuple(world_engine.get_events(instance.id))
    npc_give = send_group(
        adapter, "/give caretaker medkit", user_id=9921, chat_id=-9921
    )
    assert (
        "'caretaker' — это NPC, не игрок. "
        "GIVE/SHARE/TRADE работают только между игроками."
    ) in npc_give
    assert "Для общения с NPC — /talk в DM." in npc_give
    assert tuple(world_engine.get_events(instance.id)) == events_before_npc_give
    with uow_factory() as uow:
        assert any(
            item.key == "medkit"
            for item in uow.items.list_by_owner(
                instance.id, ItemOwnerType.CHARACTER, str(initiator_id)
            )
        )

    traded = send_group(
        adapter,
        "/trade Group_Counterparty medkit credits",
        user_id=9921,
        chat_id=-9921,
    )
    assert "action=TRADE" in traded and "ok=true" in traded
    shared = send_group(
        adapter,
        "/share Group_Counterparty dispatch_log",
        user_id=9921,
        chat_id=-9921,
    )
    assert "action=SHARE" in shared and "ok=true" in shared
    given = send_group(
        adapter,
        "/give Group_Counterparty credits",
        user_id=9921,
        chat_id=-9921,
    )
    assert "action=GIVE" in given and "ok=true" in given

    with uow_factory() as uow:
        information = uow.information.get_by_key(instance.id, "dispatch_log")
        initiator_knowledge = uow.knowledge.find(
            instance.id,
            SubjectType.CHARACTER,
            str(initiator_id),
            information.id,
        )
        counterparty_knowledge = uow.knowledge.find(
            instance.id,
            SubjectType.CHARACTER,
            str(counterparty_id),
            information.id,
        )
        inventory = uow.items.list_by_owner(
            instance.id, ItemOwnerType.CHARACTER, str(counterparty_id)
        )
    assert initiator_knowledge is not None and counterparty_knowledge is not None
    assert counterparty_knowledge.claim == initiator_knowledge.claim
    assert counterparty_knowledge.claim != catalog.information_definition("dispatch_log").truth
    assert {item.key for item in inventory} == {"credits", "medkit"}

def test_group_command_parser_fallback_resolves_trade_share_and_give(
    world_engine, uow_factory
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-9923, seed=23)
    initiator = world_engine.create_character(
        instance.id,
        player_id="9923",
        name="Fallback Initiator",
        location_key=LocationKey("base"),
    )
    counterparty = world_engine.create_character(
        instance.id,
        player_id="9924",
        name="Fallback Counterparty",
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
    adapter = TelegramAdapter(
        telegram_client=MockTelegramClient(),
        world_engine=world_engine,
        intent_interpreter=CommandIntentParser(),
        instance_resolver=GroupInstanceResolver(world_engine, uow_factory),
    )

    traded = send_group(
        adapter,
        "trade medkit to Fallback_Counterparty for credits",
        user_id=9923,
        chat_id=-9923,
    )
    assert "action=TRADE" in traded and "ok=true" in traded
    shared = send_group(
        adapter,
        "share dispatch_log with Fallback_Counterparty",
        user_id=9923,
        chat_id=-9923,
    )
    assert "action=SHARE" in shared and "ok=true" in shared
    given = send_group(
        adapter,
        "give credits to Fallback_Counterparty",
        user_id=9923,
        chat_id=-9923,
    )
    assert "action=GIVE" in given and "ok=true" in given
