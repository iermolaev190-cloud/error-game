"""Репозитории поверх SQLAlchemy Core.

Пакет разбит по агрегатам, чтобы каждый файл оставался небольшим. Имена классов
реэкспортируются из ``__init__``, поэтому внешние импорты не зависят от разбиения.

Правило изоляции: любой запрос ограничен одним ``world_instance_id``.
"""

from world_error.infrastructure.db.repositories.character import SqlCharacterRepository
from world_error.infrastructure.db.repositories.admin_user import SqlAdminUserRepository
from world_error.infrastructure.db.repositories.case import SqlCaseRepository
from world_error.infrastructure.db.repositories.chat_binding import SqlChatBindingRepository
from world_error.infrastructure.db.repositories.consequence import SqlConsequenceRepository
from world_error.infrastructure.db.repositories.event_log import SqlEventLogRepository
from world_error.infrastructure.db.repositories.faction import SqlFactionRepository
from world_error.infrastructure.db.repositories.information import SqlInformationRepository
from world_error.infrastructure.db.repositories.item import SqlItemRepository
from world_error.infrastructure.db.repositories.knowledge import SqlKnowledgeRepository
from world_error.infrastructure.db.repositories.legacy_document import SqlLegacyDocumentRepository
from world_error.infrastructure.db.repositories.location import SqlLocationStateRepository
from world_error.infrastructure.db.repositories.npc import SqlNpcRepository
from world_error.infrastructure.db.repositories.player_telegram_state import (
    SqlPlayerTelegramStateRepository,
)
from world_error.infrastructure.db.repositories.relationship import SqlRelationshipRepository
from world_error.infrastructure.db.repositories.scheduled_event import SqlScheduledEventRepository
from world_error.infrastructure.db.repositories.world_instance import SqlWorldInstanceRepository

__all__ = [
    "SqlAdminUserRepository",
    "SqlCharacterRepository",
    "SqlChatBindingRepository",
    "SqlCaseRepository",
    "SqlConsequenceRepository",
    "SqlEventLogRepository",
    "SqlFactionRepository",
    "SqlInformationRepository",
    "SqlItemRepository",
    "SqlKnowledgeRepository",
    "SqlLegacyDocumentRepository",
    "SqlLocationStateRepository",
    "SqlNpcRepository",
    "SqlPlayerTelegramStateRepository",
    "SqlRelationshipRepository",
    "SqlScheduledEventRepository",
    "SqlWorldInstanceRepository",
]
