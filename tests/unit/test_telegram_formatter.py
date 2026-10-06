from world_error.application.action_result import ActionResult
from world_error.domain.shared.kernel import DomainError, ErrorCode
from world_error.interfaces.telegram.formatter import TelegramFormatter


def test_formatter_shows_action_status_and_approved_public_fields() -> None:
    result = ActionResult.success(
        "MOVE",
        payload={
            "from": "base",
            "to": "forest",
            "world_tick": 4,
            "state_version": 3,
            "claim": "private knowledge",
            "character_id": "ch_private",
            "inventory": ["secret-item"],
        },
    )

    text = TelegramFormatter().format(result)

    assert text == (
        "action=MOVE\n"
        "ok=true\n"
        "from=base\n"
        "state_version=3\n"
        "to=forest\n"
        "world_tick=4"
    )
    assert "claim" not in text
    assert "ch_private" not in text
    assert "secret-item" not in text


def test_formatter_shows_failure_message_without_payload() -> None:
    result = ActionResult.failure(
        "MOVE",
        DomainError(ErrorCode.NOT_ALLOWED, "character cannot move"),
    )

    assert TelegramFormatter().format(result) == (
        "action=MOVE\nok=false\nerror=character cannot move"
    )


def test_formatter_translates_domain_failures_to_player_friendly_text() -> None:
    formatter = TelegramFormatter()
    messages = {
        "item is not available in a location":
            "Предмета больше нет в локации. Проверь /look и попробуй ещё раз.",
        "item is not in the character's location":
            "Предмета нет в этой локации. Проверь /look и попробуй ещё раз.",
        "character does not own this item":
            "У тебя нет этого предмета в инвентаре. Проверь /inventory в DM.",
        "characters are in different locations":
            "Вы с персонажем должны находиться в одной локации для этой команды.",
        "a character cannot trade with itself":
            "Нельзя обмениваться с самим собой. Укажи другого персонажа.",
        "NPC dialogue is not available in group chats":
            "Диалог с NPC — только в DM. Напиши боту лично: /talk <npc>.",
    }

    for source, expected in messages.items():
        result = ActionResult.failure(
            "ACTION",
            DomainError(ErrorCode.NOT_ALLOWED, source),
        )
        assert "ok=false" in formatter.format(result)
        assert f"error={expected}" in formatter.format(result)


def test_formatter_shows_curated_inspection_link() -> None:
    result = ActionResult.success(
        "INSPECT",
        payload={"external_url": "https://example.com/archive-17"},
    )

    assert "Ссылка: https://example.com/archive-17" in TelegramFormatter().format(result)
    assert "Ссылка: https://example.com/archive-17" in TelegramFormatter().format_dm(result)


def test_formatter_omits_link_when_external_url_is_absent() -> None:
    result = ActionResult.success("INSPECT", payload={"information_key": "station_test_log"})

    assert "Ссылка" not in TelegramFormatter().format(result)
    assert "Ссылка" not in TelegramFormatter().format_dm(result)
