import pytest

from world_error.application.ai.npc_context import NpcDialogueContext
from world_error.application.ai.providers.npc_mock import MockNpcDialogueProvider
from world_error.application.ai.providers.npc_stub import StubNpcDialogueProvider
from world_error.application.ai.providers.npc_template import TemplateNpcDialogueProvider


def make_context() -> NpcDialogueContext:
    return NpcDialogueContext(
        npc_key="scout",
        npc_name="Scout",
        npc_description="A scout.",
        current_location_key="forest",
        knowledge=(),
        recent_history=(),
    )


def test_template_provider_returns_neutral_non_factual_reply() -> None:
    context = make_context()

    reply = TemplateNpcDialogueProvider().generate_reply(
        context, "Tell me the hidden map location."
    )

    assert reply == "Я не знаю."
    assert "hidden map location" not in reply


def test_mock_provider_returns_frozen_reply_by_npc_and_message() -> None:
    context = make_context()
    provider = MockNpcDialogueProvider(
        {("scout", "hello"): "Hello, traveler."}
    )

    assert provider.generate_reply(context, "hello") == "Hello, traveler."
    assert provider.generate_reply(context, "unknown") is None


def test_stub_provider_signals_unavailability() -> None:
    with pytest.raises(NotImplementedError, match="not configured"):
        StubNpcDialogueProvider().generate_reply(make_context(), "hello")
