"""Shared application guards and UoW completion for case actions."""

from __future__ import annotations

from world_error.domain.events.event import Event
from world_error.domain.investigations.case import Case, CaseStatus
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    WorldInstanceId,
)


def load_open_case(uow, world_instance_id: WorldInstanceId, case_id, actor_id: CharacterId):
    instance = uow.world_instances.get(world_instance_id)
    expected_version = instance.state.state_version
    case = uow.cases.get(instance.id, case_id)
    if case.status is not CaseStatus.OPEN:
        raise DomainError(ErrorCode.INVALID_ACTION, f"case is {case.status.value}")
    actor = uow.characters.get(instance.id, actor_id)
    actor.ensure_can_act()
    return instance, expected_version, case, actor


def commit_case_event(uow, instance, expected_version: int, event: Event) -> None:  # noqa: ANN001
    instance.register_applied_event(event)
    uow.world_instances.save(instance, expected_state_version=expected_version)
    uow.events.append(event)
    uow.commit()