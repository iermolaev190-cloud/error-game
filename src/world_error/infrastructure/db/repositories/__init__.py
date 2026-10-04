"""Репозитории поверх SQLAlchemy Core.

Пакет разбит по агрегатам, чтобы каждый файл оставался небольшим. Имена классов
реэкспортируются из ``__init__``, поэтому внешние импорты не зависят от разбиения.

Правило изоляции: любой запрос ограничен одним ``world_instance_id``.
"""

from world_error.infrastructure.db.repositories.character import SqlCharacterRepository
from world_error.infrastructure.db.repositories.consequence import SqlConsequenceRepository
from world_error.infrastructure.db.repositories.event_log import SqlEventLogRepository
from world_error.infrastructure.db.repositories.information import SqlInformationRepository
from world_error.infrastructure.db.repositories.knowledge import SqlKnowledgeRepository
from world_error.infrastructure.db.repositories.location import SqlLocationStateRepository
from world_error.infrastructure.db.repositories.npc import SqlNpcRepository
from world_error.infrastructure.db.repositories.relationship import SqlRelationshipRepository
from world_error.infrastructure.db.repositories.world_instance import SqlWorldInstanceRepository

__all__ = [
    "SqlCharacterRepository",
    "SqlConsequenceRepository",
    "SqlEventLogRepository",
    "SqlInformationRepository",
    "SqlKnowledgeRepository",
    "SqlLocationStateRepository",
    "SqlNpcRepository",
    "SqlRelationshipRepository",
    "SqlWorldInstanceRepository",
]
