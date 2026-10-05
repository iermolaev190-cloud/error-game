"""Format ActionResult for group chat without exposing private payload data."""

from __future__ import annotations

from world_error.application.action_result import ActionResult


class TelegramFormatter:
    _GROUP_PAYLOAD_FIELDS = frozenset({"from", "to", "world_tick", "state_version"})

    def format(self, result: ActionResult) -> str:
        lines = [f"action={result.action}", f"ok={str(result.ok).lower()}"]
        if not result.ok:
            if result.error is not None:
                lines.append(f"error={result.error.message}")
            return "\n".join(lines)

        # Group responses only expose explicitly approved public result fields.
        for key in sorted(self._GROUP_PAYLOAD_FIELDS):
            if key in result.payload:
                lines.append(f"{key}={result.payload[key]}")
        return "\n".join(lines)
