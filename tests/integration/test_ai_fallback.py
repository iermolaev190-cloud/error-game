from types import SimpleNamespace
from pathlib import Path

from world_error.application.ai.command_parser import CommandIntentParser
from world_error.application.ai.interpreter import FallbackIntentInterpreter, IntentContext
from world_error.application.ai.providers.mock import MockIntentProvider
from world_error.application.ai.providers.stub import StubIntentProvider
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import CharacterId
from world_error.interfaces.cli.main import _dispatch, build_parser


def test_stub_provider_falls_back_to_command_parser_and_engine(world_engine) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-3001, seed=42)
    created = world_engine.create_character(instance.id, player_id="alice", name="Alice")
    assert created.ok, created.error
    actor = CharacterId(created.payload["character_id"])
    context = IntentContext(
        player_id="alice",
        character_id=actor,
        location_id="base",
        visible_objects=("medkit",),
        allowed_actions=("MOVE",),
    )
    interpreter = FallbackIntentInterpreter(StubIntentProvider(), CommandIntentParser())

    parsed = interpreter.interpret("move to forest", context)

    assert parsed is not None
    result = world_engine.handle_intent(instance.id, actor, parsed)
    assert result.ok, result.error
    assert world_engine.get_character(instance.id, actor).location_key == "forest"


def test_unparsed_cli_input_returns_explicit_failure(
    world_engine, capsys
) -> None:
    instance = world_engine.create_instance(telegram_chat_id=-3001, seed=42)
    created = world_engine.create_character(instance.id, player_id="alice", name="Alice")
    assert created.ok, created.error
    actor = CharacterId(created.payload["character_id"])
    interpreter = FallbackIntentInterpreter(StubIntentProvider(), CommandIntentParser())
    container = SimpleNamespace(world_engine=world_engine, intent_interpreter=interpreter)
    args = SimpleNamespace(
        command="interpret",
        world_id=str(instance.id),
        character_id=str(actor),
        text="tell me an unknown story",
    )

    exit_code = _dispatch(container, args)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "ERROR: INVALID_ACTION" in captured.err
    assert world_engine.get_instance(instance.id).state.world_tick == 1


def test_container_builds_configured_stub_or_mock_provider(db_url: str) -> None:
    for provider_name, provider_type in (
        ("stub", StubIntentProvider),
        ("mock", MockIntentProvider),
    ):
        container = Container.build(
            Settings(
                db_url=db_url,
                content_dir=Path("content"),
                ai_provider=provider_name,
            )
        )
        try:
            assert isinstance(container.intent_interpreter._provider, provider_type)
            assert isinstance(container.intent_interpreter._fallback, CommandIntentParser)
        finally:
            container.dispose()


def test_cli_registers_interpret_without_changing_existing_command() -> None:
    parser = build_parser()

    interpret = parser.parse_args(
        ["interpret", "--world-id", "wi_1", "--character-id", "ch_1", "--text", "move to forest"]
    )
    move = parser.parse_args(
        ["move", "--world-id", "wi_1", "--character-id", "ch_1", "--to", "forest"]
    )

    assert (interpret.command, interpret.text) == ("interpret", "move to forest")
    assert (move.command, move.to) == ("move", "forest")
