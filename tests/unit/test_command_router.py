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


def test_unknown_and_non_slash_text_routes_to_none() -> None:
    router = CommandRouter()

    assert router.route("take medkit", actor_id=ACTOR).kind == "none"
    assert router.route("/trade caretaker medkit", actor_id=ACTOR).kind == "none"


def test_command_keys_are_case_insensitive_and_normalized() -> None:
    routed = CommandRouter().route("/TAKE MedKit", actor_id=ACTOR)

    assert routed.intent is not None
    assert routed.intent.target == "medkit"
