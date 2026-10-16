"""ActionResult — результат игрового действия для интерфейса.

Игровая ошибка — часть результата, а не только доменное исключение: интерфейс
обязан показать код ошибки (INVALID_ACTION, NOT_ALLOWED, ...) без ловли
внутренних исключений (20_TECH_ARCHITECTURE_V1 §32).

Вводится в коммите 2 и используется только новыми действиями
(CREATE_CHARACTER / MOVE / INSPECT). Методы коммита 1 не переписываются.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from world_error.domain.shared.kernel import DomainError, EventId


@dataclass(frozen=True, slots=True)
class ActionResult:
    action: str
    ok: bool
    event_ids: tuple[EventId, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)
    error: DomainError | None = None

    @classmethod
    def success(
        cls,
        action: str,
        *,
        event_ids: Iterable[EventId] = (),
        payload: Mapping[str, Any] | None = None,
    ) -> "ActionResult":
        return cls(action=action, ok=True, event_ids=tuple(event_ids), payload=dict(payload or {}))

    @classmethod
    def failure(cls, action: str, error: DomainError) -> "ActionResult":
        return cls(action=action, ok=False, error=error)
