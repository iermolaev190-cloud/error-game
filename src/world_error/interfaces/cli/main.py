"""Временный CLI-интерфейс (коммиты 1–2).

Telegram здесь сознательно отсутствует: он появится отдельной фазой
(roadmap Phase 23), а интерфейс обязан быть заменяемым
(20_TECH_ARCHITECTURE_V1 §4). Игровой логики в интерфейсе нет — только вызов
World Engine и форматирование результата.

Канонический факт (``truth``) в интерфейс не выводится никогда: игрок видит
только знание персонажа (MASTER_SPEC §6).
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from world_error.application.action_result import ActionResult
from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.content.catalog import ContentError
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    LocationKey,
    WorldInstanceId,
)
from world_error.domain.world.instance import InstanceEnvironment, WorldInstance

_LIFECYCLE_CHOICES = ("ACTIVE", "PAUSED", "ARCHIVED")
_ENVIRONMENT_CHOICES = tuple(environment.value for environment in InstanceEnvironment)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="world-error",
        description="WORLD//ERROR — временный CLI (без Telegram и AI).",
    )
    parser.add_argument(
        "--db-url",
        dest="db_url",
        default=None,
        help="переопределить WORLD_ERROR_DB_URL из окружения/.env",
    )
    parser.add_argument(
        "--content-dir",
        dest="content_dir",
        default=None,
        help="переопределить каталог контента (по умолчанию content/)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-world", help="создать WORLD INSTANCE")
    create.add_argument("--chat-id", dest="chat_id", type=int, required=True)
    create.add_argument("--seed", dest="seed", type=int, default=None)
    create.add_argument("--environment", dest="environment", choices=_ENVIRONMENT_CHOICES, default="DEV")

    show = subparsers.add_parser("show-world", help="показать состояние инстанса")
    show.add_argument("instance_id")

    tick = subparsers.add_parser(
        "advance-tick", help="временный механизм коммита 1: продвинуть world_tick"
    )
    tick.add_argument("instance_id")
    tick.add_argument("--cause", dest="cause", default="manual")

    status = subparsers.add_parser("change-status", help="сменить жизненный цикл инстанса")
    status.add_argument("instance_id")
    status.add_argument("--to", dest="to", choices=_LIFECYCLE_CHOICES, required=True)
    status.add_argument("--cause", dest="cause", default="manual")

    events = subparsers.add_parser("events", help="показать журнал событий инстанса")
    events.add_argument("instance_id")

    create_character = subparsers.add_parser("create-character", help="создать персонажа")
    create_character.add_argument("--world-id", dest="world_id", required=True)
    create_character.add_argument("--player-id", dest="player_id", required=True)
    create_character.add_argument("--name", dest="name", required=True)
    create_character.add_argument("--location", dest="location", default=None)

    move = subparsers.add_parser("move", help="переместить персонажа между локациями")
    move.add_argument("--world-id", dest="world_id", required=True)
    move.add_argument("--character-id", dest="character_id", required=True)
    move.add_argument("--to", dest="to", required=True)

    inspect = subparsers.add_parser("inspect", help="исследовать информационный объект")
    inspect.add_argument("--world-id", dest="world_id", required=True)
    inspect.add_argument("--character-id", dest="character_id", required=True)
    inspect.add_argument("--target", dest="target", required=True)

    share = subparsers.add_parser("share", help="передать знание другому персонажу")
    share.add_argument("--world-id", dest="world_id", required=True)
    share.add_argument("--character-id", dest="character_id", required=True)
    share.add_argument("--to-character-id", dest="to_character_id", required=True)
    share.add_argument("--information", dest="information", required=True)

    show_character = subparsers.add_parser(
        "show-character", help="показать персонажа и его знание"
    )
    show_character.add_argument("--world-id", dest="world_id", required=True)
    show_character.add_argument("--character-id", dest="character_id", required=True)

    return parser


def _print_instance(instance: WorldInstance, *, with_details: bool = False) -> None:
    print(f"instance_id={instance.id}")
    if with_details:
        print(f"telegram_chat_id={instance.telegram_chat_id}")
        print(f"seed={instance.seed}")
        print(f"environment={instance.environment.value}")
        print(f"content_version={instance.content_version}")
    print(f"lifecycle={instance.lifecycle.value}")
    print(f"world_tick={instance.state.world_tick}")
    print(f"state_version={instance.state.state_version}")


def _print_action_result(result: ActionResult) -> int:
    if not result.ok:
        error = result.error
        code = error.code.value if error is not None else "INTERNAL_ERROR"
        message = error.message if error is not None else "unknown error"
        print(f"ERROR: {code}: {message}", file=sys.stderr)
        return 2
    for key, value in result.payload.items():
        print(f"{key}={value}")
    return 0


def _dispatch(container: Container, args: argparse.Namespace) -> int:
    world_engine = container.world_engine

    if args.command == "create-world":
        instance = world_engine.create_instance(
            args.chat_id,
            seed=args.seed,
            environment=InstanceEnvironment(args.environment),
        )
        _print_instance(instance, with_details=True)
        return 0

    if args.command == "show-world":
        _print_instance(world_engine.get_instance(WorldInstanceId(args.instance_id)))
        return 0

    if args.command == "advance-tick":
        instance = world_engine.advance_tick(WorldInstanceId(args.instance_id), cause=args.cause)
        _print_instance(instance)
        return 0

    if args.command == "change-status":
        instance = world_engine.change_status(
            WorldInstanceId(args.instance_id), to=args.to, cause=args.cause
        )
        _print_instance(instance)
        return 0

    if args.command == "events":
        events = world_engine.get_events(WorldInstanceId(args.instance_id))
        for event in events:
            printed = f"EVENT {event.id} {event.type.value} {event.created_at.isoformat()}"
            if event.result:
                printed = f"{printed} {event.result}"
            print(printed)
        print(f"events_total={len(events)}")
        return 0

    if args.command == "create-character":
        return _print_action_result(
            world_engine.create_character(
                WorldInstanceId(args.world_id),
                player_id=args.player_id,
                name=args.name,
                location_key=LocationKey(args.location) if args.location else None,
            )
        )

    if args.command == "move":
        return _print_action_result(
            world_engine.move_character(
                WorldInstanceId(args.world_id),
                character_id=CharacterId(args.character_id),
                to_location_key=LocationKey(args.to),
            )
        )

    if args.command == "inspect":
        return _print_action_result(
            world_engine.inspect_information(
                WorldInstanceId(args.world_id),
                character_id=CharacterId(args.character_id),
                target_key=args.target,
            )
        )

    if args.command == "share":
        return _print_action_result(
            world_engine.share_knowledge(
                WorldInstanceId(args.world_id),
                sharer_id=CharacterId(args.character_id),
                receiver_id=CharacterId(args.to_character_id),
                information_key=args.information,
            )
        )

    if args.command == "show-character":
        world_instance_id = WorldInstanceId(args.world_id)
        character_id = CharacterId(args.character_id)
        character = world_engine.get_character(world_instance_id, character_id)
        knowledge = world_engine.get_knowledge(world_instance_id, character_id)
        print(f"character_id={character.id}")
        print(f"world_instance_id={character.world_instance_id}")
        print(f"player_id={character.player_id}")
        print(f"name={character.name}")
        print(f"lifecycle={character.lifecycle.value}")
        print(f"activity={character.activity.value}")
        print(f"location_key={character.location_key}")
        print(f"knowledge_total={len(knowledge)}")
        for item in knowledge:
            print(f"KNOWLEDGE {item.claim_type.value} {item.confidence.value} {item.claim}")
            print(
                f"KNOWLEDGE_PROVENANCE {item.claim_type.value} {item.source.value} "
                f"{item.source_ref or '-'}"
            )
        return 0

    raise SystemExit(f"unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    overrides: dict[str, object] = {}
    if args.db_url:
        overrides["db_url"] = args.db_url
    if args.content_dir:
        overrides["content_dir"] = args.content_dir
    settings = Settings(**overrides) if overrides else Settings()

    try:
        container = Container.build(settings)
    except ContentError as exc:
        print(f"ERROR: CONTENT_ERROR: {exc}", file=sys.stderr)
        return 3

    try:
        return _dispatch(container, args)
    except DomainError as exc:
        print(f"ERROR: {exc.code.value}: {exc.message}", file=sys.stderr)
        return 2
    finally:
        container.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
