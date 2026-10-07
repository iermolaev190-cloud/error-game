import asyncio
from dataclasses import dataclass

import pytest

from world_error.application.action_result import ActionResult
from world_error.domain.shared.kernel import WorldInstanceId
from world_error.interfaces.telegram.registration_handler import (
    RegistrationStates,
    RegistrationTelegramHandler,
)


@dataclass
class FakeFSMContext:
    data: dict[str, object]
    current_state: object | None = None

    async def clear(self) -> None:
        self.data.clear()
        self.current_state = None

    async def update_data(self, **kwargs: object) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def set_state(self, state: object) -> None:
        self.current_state = state


class FakeResolver:
    def __init__(self, instance_id: str) -> None:
        self.instance_id = WorldInstanceId(instance_id)

    def resolve_dm_instance(self, telegram_user_id: int) -> WorldInstanceId:
        return self.instance_id

    def resolve_dm_character(self, telegram_user_id: int, instance_id):
        return None


class FakeWorldEngine:
    def __init__(self) -> None:
        self.create_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def find_active_character_for_player(self, world_instance_id, player_id):
        return None

    def create_character(self, *args, **kwargs):
        self.create_calls.append((args, kwargs))
        return ActionResult.success(
            "CREATE_CHARACTER",
            payload={
                "name": kwargs["name"],
                "location_key": "base",
            },
        )


def test_registration_states_cover_confirmation_name_and_completion() -> None:
    assert RegistrationStates.confirm.state
    assert RegistrationStates.awaiting_name.state
    assert RegistrationStates.done.state
    assert RegistrationStates.confirm != RegistrationStates.awaiting_name
    assert RegistrationStates.awaiting_name != RegistrationStates.done


def test_registration_creates_character_in_selected_world_as_system() -> None:
    engine = FakeWorldEngine()
    handler = RegistrationTelegramHandler(
        world_engine=engine,
        instance_resolver=FakeResolver("wi_selected"),
    )
    state = FakeFSMContext(data={})

    start_response = asyncio.run(
        handler.start(telegram_user_id=123, state=state)
    )
    confirmation = asyncio.run(
        handler.confirm(telegram_user_id=123, text="Да", state=state)
    )
    response = asyncio.run(
        handler.create_character(telegram_user_id=123, text="Ada", state=state)
    )

    assert start_response == "У тебя нет character. Создать? Ответь «Да» или «Отмена»."
    assert confirmation == "Как тебя зовут?"
    assert response == "Привет, Ada! Локация: base. /help."
    assert engine.create_calls == [
        (
            (WorldInstanceId("wi_selected"),),
            {"player_id": "123", "name": "Ada", "actor": "system"},
        )
    ]
    assert state.current_state == RegistrationStates.done


@pytest.mark.parametrize("answer", ["Отмена", "Нет"])
def test_registration_cancellation_clears_fsm(answer: str) -> None:
    handler = RegistrationTelegramHandler(
        world_engine=FakeWorldEngine(),
        instance_resolver=FakeResolver("wi_selected"),
    )
    state = FakeFSMContext(
        data={"world_instance_id": "wi_selected"},
        current_state=RegistrationStates.confirm,
    )

    response = asyncio.run(
        handler.confirm(telegram_user_id=123, text=answer, state=state)
    )

    assert response == "Ок. Напиши /start позже."
    assert state.current_state is None
    assert state.data == {}
