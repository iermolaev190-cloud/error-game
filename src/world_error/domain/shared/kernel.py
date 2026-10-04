"""Ядро domain-слоя: идентификаторы, игровые ошибки, общие перечисления, время.

Здесь допускается только стандартная библиотека.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import NewType, Protocol

WorldInstanceId = NewType("WorldInstanceId", str)
EventId = NewType("EventId", str)
CharacterId = NewType("CharacterId", str)
InformationId = NewType("InformationId", str)
KnowledgeId = NewType("KnowledgeId", str)
NpcId = NewType("NpcId", str)
LocationKey = NewType("LocationKey", str)


def new_world_instance_id() -> WorldInstanceId:
    """Новый идентификатор WORLD INSTANCE."""
    return WorldInstanceId(f"wi_{uuid.uuid4().hex}")


def new_event_id() -> EventId:
    """Новый идентификатор события."""
    return EventId(f"ev_{uuid.uuid4().hex}")


def new_character_id() -> CharacterId:
    """Новый идентификатор персонажа."""
    return CharacterId(f"ch_{uuid.uuid4().hex}")


def new_information_id() -> InformationId:
    """Новый идентификатор информационного объекта мира."""
    return InformationId(f"info_{uuid.uuid4().hex}")


def new_knowledge_id() -> KnowledgeId:
    """Новый идентификатор записи знания."""
    return KnowledgeId(f"kn_{uuid.uuid4().hex}")


def new_npc_id() -> NpcId:
    """Новый идентификатор NPC."""
    return NpcId(f"npc_{uuid.uuid4().hex}")


class DiscoveryState(StrEnum):
    """Состояние мира: «кто-то из существ уже был здесь / уже нашёл это».

    Различаем EXISTENCE, VISIBILITY, KNOWLEDGE и ACCESS (11_WORLD_STATE_V1 §30).
    ``discovery_state`` описывает мир, а не знание конкретного субъекта: знание
    живёт отдельно, в Knowledge, и не выводится автоматически.
    """

    UNDISCOVERED = "UNDISCOVERED"
    DISCOVERED = "DISCOVERED"


class ErrorCode(StrEnum):
    """Коды игровых ошибок (20_TECH_ARCHITECTURE_V1 §32).

    Игровая ошибка отличается от системной: она не должна менять состояние
    мира частично и должна иметь понятный путь обработки.
    """

    INVALID_ACTION = "INVALID_ACTION"
    NOT_FOUND = "NOT_FOUND"
    NOT_ALLOWED = "NOT_ALLOWED"
    INSUFFICIENT_RESOURCE = "INSUFFICIENT_RESOURCE"
    CONFLICT = "CONFLICT"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DomainError(Exception):
    """Игровая ошибка с кодом."""

    def __init__(self, code: ErrorCode, message: str = "") -> None:
        self.code = code
        self.message = message or code.value
        super().__init__(f"{self.code.value}: {self.message}")


class Clock(Protocol):
    """Источник времени. Инжектируется, чтобы тесты были детерминированными."""

    def now(self) -> datetime: ...


class SystemClock:
    """Реальные часы в UTC."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
