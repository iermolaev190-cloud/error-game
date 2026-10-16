from world_error.application.ai.command_router import CommandRouter
from world_error.application.ai.intent import IntentType
from world_error.domain.shared.kernel import CharacterId


ACTOR = CharacterId("ch_test")


def test_action_commands_route_to_expected_intents() -> None:
    router = CommandRouter()
    expected = (
        ("/move forest", IntentType.MOVE, "forest"),
        ("/inspect radio", IntentType.INSPECT, "radio"),
        ("/take medkit", IntentType.TAKE, "medkit"),
        ("/drop medkit", IntentType.DROP, "medkit"),
        ("/talk caretaker", IntentType.TALK, "caretaker"),
        ("/give alice medkit", IntentType.GIVE, "alice"),
        ("/share alice dispatch_log", IntentType.SHARE_KNOWLEDGE, "alice"),
        ("/trade alice medkit flashlight", IntentType.TRADE, "alice"),
    )

    for text, intent_type, target in expected:
        routed = router.route(text, actor_id=ACTOR)
        assert routed.kind == "intent"
        assert routed.intent is not None
        assert routed.intent.type is intent_type
        assert routed.intent.actor_id == ACTOR
        assert routed.intent.target == target


def test_talk_command_uses_neutral_default_message() -> None:
    routed = CommandRouter().route("/talk caretaker", actor_id=ACTOR)

    assert routed.intent is not None
    assert routed.intent.params["message"] == "Привет. О чём поговорим?"


def test_give_share_and_trade_commands_route_parameters() -> None:
    router = CommandRouter()

    give = router.route("/give Alice MedKit", actor_id=ACTOR).intent
    share = router.route("/share Alice Dispatch_Log", actor_id=ACTOR).intent
    trade = router.route("/trade Alice MedKit Flashlight", actor_id=ACTOR).intent

    assert give is not None and dict(give.params) == {"item_key": "medkit"}
    assert share is not None and dict(share.params) == {"information_key": "dispatch_log"}
    assert trade is not None and dict(trade.params) == {
        "offered_item_key": "medkit",
        "requested_item_key": "flashlight",
    }


def test_unknown_and_non_slash_text_routes_to_none() -> None:
    router = CommandRouter()

    assert router.route("take medkit", actor_id=ACTOR).kind == "none"
    assert router.route("/trade caretaker medkit", actor_id=ACTOR).kind == "none"


def test_command_keys_are_case_insensitive_and_normalized() -> None:
    routed = CommandRouter().route("/TAKE MedKit", actor_id=ACTOR)

    assert routed.intent is not None
    assert routed.intent.target == "medkit"


def test_character_names_can_contain_cyrillic_letters() -> None:
    routed = CommandRouter().route("/give Иван medkit", actor_id=ACTOR)

    assert routed.intent is not None
    assert routed.intent.type is IntentType.GIVE
    assert routed.intent.target == "иван"
    assert dict(routed.intent.params) == {"item_key": "medkit"}


def test_slash_commands_ignore_bot_username() -> None:
    router = CommandRouter()

    give = router.route("/give@BotUsername scout medkit", actor_id=ACTOR)
    move = router.route("/move@BotUsername forest", actor_id=ACTOR)
    look = router.route("/look@BotUsername", actor_id=ACTOR)

    assert give.kind == "intent"
    assert give.intent is not None
    assert give.intent.type is IntentType.GIVE
    assert give.intent.target == "scout"
    assert dict(give.intent.params) == {"item_key": "medkit"}
    assert move.kind == "intent"
    assert move.intent is not None
    assert move.intent.type is IntentType.MOVE
    assert move.intent.target == "forest"
    assert look.kind == "query"
    assert look.query_type == "look"

    assert router.route("/move forest", actor_id=ACTOR).intent is not None
    assert router.route("take medkit", actor_id=ACTOR).kind == "none"
