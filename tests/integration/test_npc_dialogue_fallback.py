from world_error.application.ai.intent import Intent, IntentType
from world_error.application.ai.providers.npc_mock import MockNpcDialogueProvider
from world_error.application.ai.providers.npc_stub import StubNpcDialogueProvider
from world_error.application.ai.providers.npc_template import TemplateNpcDialogueProvider
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import CharacterId, LocationKey, WorldInstanceId
from world_error.interfaces.cli.main import build_parser


def test_missing_provider_reply_uses_neutral_template(make_world_engine) -> None:
    engine = make_world_engine(
        MockNpcDialogueProvider({("caretaker", "hello"): None})
    )
    instance = engine.create_instance(telegram_chat_id=-8201, seed=82)
    caretaker = next(
        npc for npc in engine.get_npcs(instance.id) if npc.key == "caretaker"
    )
    created = engine.create_character(
        instance.id,
        player_id="alice",
        name="Alice",
        location_key=LocationKey(str(caretaker.location_key)),
    )
    assert created.ok, created.error

    result = engine.talk_to_npc(
        instance.id,
        character_id=CharacterId(created.payload["character_id"]),
        npc_id=caretaker.id,
        message="hello",
    )

    assert result.ok, result.error
    assert result.payload["reply"] == "Я не знаю."


def test_unavailable_stub_provider_falls_back_without_failure(make_world_engine) -> None:
    engine = make_world_engine(StubNpcDialogueProvider())
    instance = engine.create_instance(telegram_chat_id=-8202, seed=83)
    caretaker = next(
        npc for npc in engine.get_npcs(instance.id) if npc.key == "caretaker"
    )
    created = engine.create_character(
        instance.id,
        player_id="alice",
        name="Alice",
        location_key=LocationKey(str(caretaker.location_key)),
    )
    assert created.ok, created.error

    result = engine.handle_intent(
        instance.id,
        CharacterId(created.payload["character_id"]),
        Intent(
            type=IntentType.TALK,
            actor_id=CharacterId(created.payload["character_id"]),
            target=str(caretaker.id),
            params={"message": "hello"},
        ),
    )

    assert result.ok, result.error
    assert result.payload["reply"] == "Я не знаю."


def test_talk_cli_arguments_are_registered() -> None:
    args = build_parser().parse_args(
        [
            "talk",
            "--world-id",
            "wi_test",
            "--character-id",
            "ch_test",
            "--npc-id",
            "npc_test",
            "--text",
            "hello",
        ]
    )

    assert args.command == "talk"
    assert args.text == "hello"


def test_container_uses_template_provider_by_default(tmp_path) -> None:
    container = Container.build(
        Settings(db_url=f"sqlite+pysqlite:///{tmp_path / 'dialogue.db'}")
    )
    try:
        assert isinstance(container.npc_dialogue_provider, TemplateNpcDialogueProvider)
    finally:
        container.dispose()


def test_container_selects_stub_and_mock_npc_providers(tmp_path) -> None:
    for provider_name, expected_type in (
        ("stub", StubNpcDialogueProvider),
        ("mock", MockNpcDialogueProvider),
    ):
        container = Container.build(
            Settings(
                db_url=f"sqlite+pysqlite:///{tmp_path / (provider_name + '.db')}",
                npc_dialogue_provider=provider_name,
            )
        )
        try:
            assert isinstance(container.npc_dialogue_provider, expected_type)
        finally:
            container.dispose()


def test_talk_cli_executes_with_default_template_provider(
    db_url, alembic_upgrade, cli
) -> None:
    upgrade = alembic_upgrade(db_url)
    assert upgrade.returncode == 0, upgrade.stderr
    created_world = cli(db_url, "create-world", "--chat-id", "-8203", "--seed", "84")
    assert created_world.returncode == 0, created_world.stderr
    world_id = next(
        line.split("=", 1)[1]
        for line in created_world.stdout.splitlines()
        if line.startswith("instance_id=")
    )
    created_character = cli(
        db_url,
        "create-character",
        "--world-id",
        world_id,
        "--player-id",
        "cli-player",
        "--name",
        "CLI Player",
    )
    assert created_character.returncode == 0, created_character.stderr
    character_id = next(
        line.split("=", 1)[1]
        for line in created_character.stdout.splitlines()
        if line.startswith("character_id=")
    )
    container = Container.build(Settings(db_url=db_url))
    try:
        npc = next(
            npc
            for npc in container.world_engine.get_npcs(WorldInstanceId(world_id))
            if npc.key == "caretaker"
        )
        npc_id = str(npc.id)
    finally:
        container.dispose()

    result = cli(
        db_url,
        "talk",
        "--world-id",
        world_id,
        "--character-id",
        character_id,
        "--npc-id",
        npc_id,
        "--text",
        "hello",
    )

    assert result.returncode == 0, result.stderr
    assert "reply=Я не знаю." in result.stdout
