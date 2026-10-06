"""Format ActionResult with separate public and private allowlists."""

from __future__ import annotations

from world_error.application.action_result import ActionResult


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
