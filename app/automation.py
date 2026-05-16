from __future__ import annotations

from datetime import datetime, timezone


def build_status_row(message: str, source: str, timestamp: datetime | None = None) -> list[str]:
    """Build the starter automation row written to Google Sheets."""
    occurred_at = timestamp or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    return [
        occurred_at.astimezone(timezone.utc).isoformat(),
        source,
        message,
    ]

