"""Временный CLI-интерфейс коммита 1.

Telegram здесь сознательно отсутствует: он появится отдельной фазой
(roadmap Phase 23), а интерфейс обязан быть заменяемым
(20_TECH_ARCHITECTURE_V1 §4). Игровой логики в интерфейсе нет — только вызов
World Engine и форматирование результата.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from world_error.bootstrap.config import Settings
from world_error.bootstrap.container import Container
from world_error.domain.shared.kernel import DomainError, WorldInstanceId
from world_error.domain.world.instance import InstanceEnvironment, WorldInstance

_LIFECYCLE_CHOICES = ("ACTIVE", "PAUSED", "ARCHIVED")
_ENVIRONMENT_CHOICES = tuple(environment.value for environment in InstanceEnvironment)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="world-error",
        description="WORLD//ERROR — временный CLI коммита 1 (без Telegram и AI).",
    )
    parser.add_argument(
        "--db-url",
        dest="db_url",
        default=None,
        help="переопределить WORLD_ERROR_DB_URL из окружения/.env",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create-world", help="создать WORLD INSTANCE")
    create.add_argument("--chat-id", dest="chat_id", type=int, required=True)
    create.add_argument("--seed", dest="seed", type=int, default=None)
    create.add_argument("--environment", dest="environment", choices=_ENVIRONMENT_CHOICES, default="DEV")

    show = subparsers.add_parser("show-world", help="показать состояние инстанса")
    show.add_argument("instance_id")

    tick = subparsers.add_parser("advance-tick", help="временный механизм: продвинуть world_tick")
    tick.add_argument("instance_id")
    tick.add_argument("--cause", dest="cause", default="manual")

    status = subparsers.add_parser("change-status", help="сменить жизненный цикл инстанса")
    status.add_argument("instance_id")
    status.add_argument("--to", dest="to", choices=_LIFECYCLE_CHOICES, required=True)
    status.add_argument("--cause", dest="cause", default="manual")

    events = subparsers.add_parser("events", help="показать журнал событий инстанса")
    events.add_argument("instance_id")

    return parser


def _print_instance(instance: WorldInstance, *, with_details: bool = False) -> None:
    print(f"instance_id={instance.id}")
    if with_details:
        print(f"telegram_chat_id={instance.telegram_chat_id}")
        print(f"seed={instance.seed}")
        print(f"environment={instance.environment.value}")
    print(f"lifecycle={instance.lifecycle.value}")
    print(f"world_tick={instance.state.world_tick}")
    print(f"state_version={instance.state.state_version}")


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

    raise SystemExit(f"unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings(db_url=args.db_url) if args.db_url else Settings()
    container = Container.build(settings)
    try:
        return _dispatch(container, args)
    except DomainError as exc:
        print(f"ERROR: {exc.code.value}: {exc.message}", file=sys.stderr)
        return 2
    finally:
        container.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
