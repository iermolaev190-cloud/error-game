"""Unit tests for the INSPECT action result payload."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from world_error.application.commands.inspect_information import (
    InspectInformationCommand,
    InspectInformationHandler,
)
from world_error.domain.information.information import Information, InformationDefinition
from world_error.domain.shared.kernel import (
    CharacterId,
    InformationId,
    LocationKey,
    WorldInstanceId,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
WORLD_ID = WorldInstanceId("wi_inspect")
CHARACTER_ID = CharacterId("ch_inspect")
LOCATION_KEY = LocationKey("old_station")
EXTERNAL_URL = "https://example.com/archive-17"


def test_inspect_returns_external_url_without_adding_it_to_event_payload() -> None:
    information = Information(
        id=InformationId("info_inspect"),
        world_instance_id=WORLD_ID,
        key="damaged_radio",
        location_key=LOCATION_KEY,
    )
    definition = InformationDefinition(
        key="damaged_radio",
        location_key=LOCATION_KEY,
        information_type="DEVICE",
        source="PHYSICAL_OBJECT",
        authenticity="AUTHENTIC",
        access="OPEN",
        content="The radio is damaged.",
        truth="The radio was damaged deliberately.",
        external_url=EXTERNAL_URL,
    )
    character = SimpleNamespace(
        id=CHARACTER_ID,
        world_instance_id=WORLD_ID,
        location_key=LOCATION_KEY,
        ensure_can_act=MagicMock(),
    )
    instance = SimpleNamespace(
        id=WORLD_ID,
        state=SimpleNamespace(world_tick=1, state_version=1),
        register_applied_event=MagicMock(),
    )
    uow = MagicMock()
    uow.__enter__.return_value = uow
    uow.world_instances.get.return_value = instance
    uow.characters.get.return_value = character
    uow.information.get_by_key.return_value = information
    uow.knowledge.find.return_value = None

    catalog = MagicMock()
    catalog.information_definition.return_value = definition
    clock = MagicMock()
    clock.now.return_value = NOW
    handler = InspectInformationHandler(
        uow_factory=lambda: uow,
        clock=clock,
        catalog=catalog,
    )

    result = handler.handle(
        InspectInformationCommand(
            world_instance_id=WORLD_ID,
            character_id=CHARACTER_ID,
            target_key="damaged_radio",
        )
    )

    assert result.ok
    assert result.payload["external_url"] == EXTERNAL_URL
    recorded_event = uow.events.append.call_args.args[0]
    assert "external_url" not in recorded_event.payload
    assert set(result.payload) == {
        "already_known",
        "information_key",
        "claim",
        "claim_type",
        "source",
        "confidence",
        "document_date",
        "world_tick",
        "state_version",
        "cost_ticks",
        "external_url",
    }
