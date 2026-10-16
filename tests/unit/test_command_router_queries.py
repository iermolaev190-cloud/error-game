from world_error.application.ai.command_router import CommandRouter
from world_error.domain.shared.kernel import CharacterId


def test_queries_are_not_routed_as_intents() -> None:
    router = CommandRouter()
    actor_id = CharacterId("ch_test")

    for command, query_type in (
        ("/look", "look"),
        ("/npcs", "npcs"),
        ("/inventory", "inventory"),
        ("/knowledge", "knowledge"),
        ("/character", "character"),
        ("/help", "help"),
    ):
        routed = router.route(command, actor_id=actor_id)
        assert routed.kind == "query"
        assert routed.intent is None
        assert routed.query_type == query_type


def test_queries_carry_no_world_data_or_extra_parameters() -> None:
    routed = CommandRouter().route(
        "/inventory",
        actor_id=CharacterId("ch_test"),
    )

    assert routed.kind == "query"
    assert dict(routed.query_params) == {}
