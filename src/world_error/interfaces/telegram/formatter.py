"""Format ActionResult with separate public and private allowlists."""

from __future__ import annotations

from collections.abc import Sequence

from world_error.application.action_result import ActionResult
from world_error.application.queries.inventory_view import InventoryView
from world_error.application.queries.location_view import LocationView
from world_error.domain.characters.character import Character
from world_error.domain.knowledge.knowledge import Knowledge


class TelegramFormatter:
    _GROUP_PAYLOAD_FIELDS = frozenset({"from", "to", "world_tick", "state_version"})
    _DM_PAYLOAD_FIELDS = _GROUP_PAYLOAD_FIELDS | frozenset(
        {
            "claim",
            "claim_type",
            "confidence",
            "document_date",
            "reply",
            "inventory",
            "knowledge",
        }
    )
    _PRIVATE_ITEM_FIELDS = ("name", "quantity", "description")
    _PRIVATE_KNOWLEDGE_FIELDS = (
        "claim",
        "claim_type",
        "confidence",
        "document_date",
    )

    def format(self, result: ActionResult) -> str:
        return self._format(result, self._GROUP_PAYLOAD_FIELDS)

    def format_dm(self, result: ActionResult) -> str:
        return self._format(result, self._DM_PAYLOAD_FIELDS)

    @staticmethod
    def format_location(view: LocationView) -> str:
        npcs = ", ".join(item.name for item in view.npcs) or "none"
        items = ", ".join(item.name for item in view.items) or "none"
        connections = ", ".join(view.connections) or "none"
        return "\n".join(
            (
                f"location={view.name} ({view.location_key})",
                f"description={view.description}",
                f"npcs={npcs}",
                f"items={items}",
                f"exits={connections}",
            )
        )

    @staticmethod
    def format_npcs(view: LocationView) -> str:
        names = ", ".join(item.name for item in view.npcs) or "none"
        return f"npcs={names}"

    @staticmethod
    def format_inventory(inventory: InventoryView) -> str:
        lines = ["inventory"]
        if not inventory.items:
            lines.append("items=none")
        for item in inventory.items:
            lines.append(
                f"item: name={item.name}, quantity={item.quantity}, description={item.description}"
            )
        return "\n".join(lines)

    @staticmethod
    def format_character(character: Character) -> str:
        return "\n".join(
            (
                f"character={character.name}",
                f"location={character.location_key}",
                f"lifecycle={character.lifecycle.value}",
                f"activity={character.activity.value}",
            )
        )

    @staticmethod
    def format_knowledge(knowledge: Sequence[Knowledge]) -> str:
        lines = ["knowledge"]
        if not knowledge:
            lines.append("claims=none")
        for record in knowledge:
            document_date = (
                "" if record.document_date is None else f", document_date={record.document_date.isoformat()}"
            )
            lines.append(
                f"claim={record.claim}, claim_type={record.claim_type.value}, "
                f"confidence={record.confidence.value}{document_date}"
            )
        return "\n".join(lines)

    @staticmethod
    def format_help(*, private: bool) -> str:
        commands = [
            "/move <loc>",
            "/inspect <target>",
            "/take <item>",
            "/drop <item>",
            "/look",
            "/npcs",
            "/help",
        ]
        if private:
            commands.extend(
                ("/inventory", "/knowledge", "/character", "/talk <npc>")
            )
        return "commands:\n" + "\n".join(commands)

    def _format(self, result: ActionResult, allowed_fields: frozenset[str]) -> str:
        lines = [f"action={result.action}", f"ok={str(result.ok).lower()}"]
        if not result.ok:
            if result.error is not None:
                lines.append(f"error={result.error.message}")
            return "\n".join(lines)

        # Never render arbitrary payload data, especially in public group chats.
        for key in sorted(allowed_fields):
            if key in result.payload:
                value = result.payload[key]
                if key == "inventory":
                    lines.extend(self._format_records("item", value, self._PRIVATE_ITEM_FIELDS))
                elif key == "knowledge":
                    lines.extend(
                        self._format_records(
                            "knowledge", value, self._PRIVATE_KNOWLEDGE_FIELDS
                        )
                    )
                else:
                    lines.append(f"{key}={value}")
        return "\n".join(lines)

    @staticmethod
    def _format_records(
        label: str, records: object, fields: tuple[str, ...]
    ) -> list[str]:
        if not isinstance(records, (tuple, list)):
            return []
        lines = []
        for record in records:
            if not isinstance(record, dict):
                continue
            values = [
                f"{field}={record[field]}"
                for field in fields
                if field in record and record[field] is not None
            ]
            if values:
                lines.append(f"{label}: " + ", ".join(values))
        return lines
