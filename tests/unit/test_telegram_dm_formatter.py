from world_error.application.action_result import ActionResult
from world_error.interfaces.telegram.formatter import TelegramFormatter


def test_dm_formatter_shows_private_knowledge_and_inventory_fields() -> None:
    result = ActionResult.success(
        "PRIVATE_VIEW",
        payload={
            "claim": "The radio is damaged.",
            "inventory": (
                {
                    "name": "Medkit",
                    "quantity": 2,
                    "description": "A medical kit.",
                    "owner_id": "hidden-owner",
                },
            ),
            "knowledge": (
                {
                    "claim": "A signal was heard.",
                    "claim_type": "FACT",
                    "confidence": "LIKELY",
                    "document_date": None,
                    "truth": "world truth",
                },
            ),
            "world_instance_id": "private-instance-id",
        },
    )

    text = TelegramFormatter().format_dm(result)

    assert "claim=The radio is damaged." in text
    assert "item: name=Medkit, quantity=2, description=A medical kit." in text
    assert "knowledge: claim=A signal was heard., claim_type=FACT, confidence=LIKELY" in text
    assert "owner_id" not in text
    assert "truth" not in text
    assert "private-instance-id" not in text


def test_group_formatter_never_shows_dm_private_fields() -> None:
    result = ActionResult.success(
        "PRIVATE_VIEW",
        payload={
            "claim": "Secret claim",
            "reply": "Secret reply",
            "inventory": ({"name": "Secret item", "quantity": 1},),
            "knowledge": ({"claim": "Secret knowledge"},),
        },
    )

    text = TelegramFormatter().format(result)

    assert text == "action=PRIVATE_VIEW\nok=true"
    assert "Secret" not in text
