"""Разрешение ссылок на субъектов мира внутри одного INSTANCE.

Отдельный модуль, потому что три обработчика (отношения и гейт в ``npc_learn``)
делают одну и ту же проверку: субъект поддерживается доменом и существует
именно в этом мире.
"""

from __future__ import annotations

from world_error.domain.characters.character import CharacterLifecycle
from world_error.domain.knowledge.knowledge import SubjectType
from world_error.domain.relationships.relationship import (
    SubjectRef,
    ensure_supported_subject_type,
)
from world_error.domain.shared.kernel import (
    CharacterId,
    DomainError,
    ErrorCode,
    NpcId,
    WorldInstanceId,
)


def resolve_subject(uow, world_instance_id: WorldInstanceId, subject: SubjectRef) -> None:
    """Проверить субъекта: поддерживаемый тип и существование в своём INSTANCE.

    Чужой мир сюда не попадёт: репозитории ограничены ``world_instance_id``,
    поэтому субъект другого INSTANCE даёт ``NOT_FOUND``.
    """
    ensure_supported_subject_type(subject)
    if subject.type is SubjectType.CHARACTER:
        uow.characters.get(world_instance_id, CharacterId(subject.id))
        return
    if subject.type is SubjectType.NPC:
        uow.npcs.get(world_instance_id, NpcId(subject.id))
        return
    raise DomainError(
        ErrorCode.INVALID_ACTION,
        f"unsupported relationship subject type: {subject.type}",
    )


def ensure_relationship_subject_alive(uow, world_instance_id: WorldInstanceId, subject: SubjectRef) -> None:
    """A dead character remains in history but cannot participate in new relations."""
    if subject.type is SubjectType.CHARACTER:
        character = uow.characters.get(world_instance_id, CharacterId(subject.id))
        if character.lifecycle is CharacterLifecycle.DEAD:
            raise DomainError(
                ErrorCode.NOT_ALLOWED,
                f"dead character {character.id} cannot participate in relationship changes",
            )


def subject_ref_from_id(subject_id: str) -> SubjectRef | None:
    """Определить тип субъекта по префиксу идентификатора.

    Идентификаторы namespace-префиксные (``ch_``/``npc_``), поэтому тип
    однозначен. Для ссылок иного вида (например, ``document_17``) возвращаем
    ``None``: это не субъект, и проверять отношение не к кому.
    """
    if subject_id.startswith("ch_"):
        return SubjectRef(type=SubjectType.CHARACTER, id=subject_id)
    if subject_id.startswith("npc_"):
        return SubjectRef(type=SubjectType.NPC, id=subject_id)
    return None
