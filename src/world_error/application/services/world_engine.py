"""World Engine — точка входа application-слоя.

Каждый игровой запрос приходит сюда с обязательным ``world_instance_id``
(20_TECH_ARCHITECTURE_V1 §5) и проходит один путь: загрузка состояния →
создание EVENT → применение правил domain → запись состояния и события в одной
транзакции.

Это не God Object: движок не знает про Telegram, AI и SQL, не содержит правил
мира и не управляет чужими подсистемами. Правила живут в domain, хранение — за
портами (MASTER_SPEC §3.10, 20_TECH_ARCHITECTURE_V1 §29).
"""

from __future__ import annotations

import secrets
from typing import Any, Callable, Mapping, Sequence

from world_error.application.commands.create_world_instance import (
    CreateWorldInstanceCommand,
    CreateWorldInstanceHandler,
)
from world_error.application.ports.repositories import UnitOfWorkFactory
from world_error.domain.events.event import Event, EventType
from world_error.domain.shared.kernel import (
    Clock,
    DomainError,
    ErrorCode,
    EventId,
    SystemClock,
    WorldInstanceId,
    new_event_id,
)
from world_error.domain.world.instance import InstanceEnvironment, InstanceLifecycle, WorldInstance

DEFAULT_SEED_BITS = 63


class WorldEngine:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock | None = None,
        new_event_id_factory: Callable[[], EventId] = new_event_id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock or SystemClock()
        self._new_event_id = new_event_id_factory
        self._create_world_instance = CreateWorldInstanceHandler(
            uow_factory=uow_factory,
            clock=self._clock,
            new_event_id_factory=self._new_event_id,
        )

    # --- команды -----------------------------------------------------------

    def create_instance(
        self,
        telegram_chat_id: int,
        *,
        seed: int | None = None,
        environment: InstanceEnvironment = InstanceEnvironment.DEV,
        actor: str = "system",
    ) -> WorldInstance:
        """Создать WORLD INSTANCE.

        ``seed`` хранится в инстансе: он нужен, чтобы случайность в будущем
        была воспроизводимой (20_TECH_ARCHITECTURE_V1 §25).
        """
        if seed is None:
            seed = secrets.randbits(DEFAULT_SEED_BITS)
        return self._create_world_instance.handle(
            CreateWorldInstanceCommand(
                telegram_chat_id=telegram_chat_id,
                seed=seed,
                environment=environment,
                actor=actor,
            )
        )

    def advance_tick(self, world_instance_id: WorldInstanceId, *, cause: str = "manual") -> WorldInstance:
        """Продвинуть мировой тик на 1 и записать ``WORLD_TICK_ADVANCED``.

        ВРЕМЕННЫЙ механизм коммита 1 "Фундамент": он нужен только чтобы
        проверить event-driven переход состояния и восстановление после
        перезапуска процесса без игрового контента. В дальнейшем ``world_tick``
        будет увеличиваться как часть обработки произвольного EVENT, а не
        отдельным событием.
        """
        return self._apply(
            world_instance_id,
            EventType.WORLD_TICK_ADVANCED,
            cause=cause,
            target=str(world_instance_id),
            payload_factory=lambda instance: {
                "from_tick": instance.state.world_tick,
                "to_tick": instance.state.world_tick + 1,
            },
        )

    def change_status(
        self,
        world_instance_id: WorldInstanceId,
        *,
        to: InstanceLifecycle | str,
        cause: str = "manual",
    ) -> WorldInstance:
        """Сменить жизненный цикл инстанса.

        Идёт через тот же Unit of Work, что и остальные изменения: админских
        путей в обход транзакции нет.
        """
        target = InstanceLifecycle(to)
        return self._apply(
            world_instance_id,
            EventType.WORLD_INSTANCE_STATUS_CHANGED,
            cause=cause,
            target=str(world_instance_id),
            payload_factory=lambda instance: {"from": instance.lifecycle.value, "to": target.value},
        )

    # --- запросы -----------------------------------------------------------

    def get_instance(self, world_instance_id: WorldInstanceId) -> WorldInstance:
        with self._uow_factory() as uow:
            return uow.world_instances.get(world_instance_id)

    def get_events(self, world_instance_id: WorldInstanceId) -> Sequence[Event]:
        with self._uow_factory() as uow:
            uow.world_instances.get(world_instance_id)  # NOT_FOUND вместо пустого списка
            return list(uow.events.list_for_instance(world_instance_id))

    # --- внутреннее --------------------------------------------------------

    def _apply(
        self,
        world_instance_id: WorldInstanceId,
        event_type: EventType,
        *,
        cause: str,
        target: str | None,
        payload_factory: Callable[[WorldInstance], Mapping[str, Any]],
        actor: str = "system",
    ) -> WorldInstance:
        with self._uow_factory() as uow:
            instance = uow.world_instances.get(world_instance_id)
            now = self._clock.now()
            event = Event(
                id=self._new_event_id(),
                world_instance_id=world_instance_id,
                type=event_type,
                created_at=now,
                # В коммите 1 применение мгновенное, поэтому executed_at == created_at.
                # Разделение понадобится для отложенных (scheduled) событий.
                executed_at=now,
                actor=actor,
                target=target,
                cause=cause,
                payload=dict(payload_factory(instance)),
                result="success",
            )
            if uow.events.has_event(world_instance_id, event.id):
                raise DomainError(ErrorCode.ALREADY_PROCESSED, f"event already processed: {event.id}")

            instance.apply(event)          # правила domain; при ошибке — откат
            uow.events.append(event)       # идемпотентность и append-only
            uow.world_instances.save(instance)
            uow.commit()
        return instance
