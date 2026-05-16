from __future__ import annotations

import argparse
from datetime import datetime, timezone

from app.automation import build_status_row
from app.config import Settings
from app.operation_log import try_append_operation_log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the PSR AIOS Google Sheets automation starter."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the row that would be written without calling Google Sheets.",
    )
    parser.add_argument(
        "--message",
        default="PSR AIOS v1 started",
        help="Message to append to the target worksheet.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings.from_env(require_google=not args.dry_run)
    row = build_status_row(
        message=args.message,
        source=settings.project_name,
        timestamp=datetime.now(timezone.utc),
    )

    if args.dry_run:
        print(f"Dry run row: {row}")
        return

    from app.sheets import GoogleSheetsClient

    client = GoogleSheetsClient.from_settings(settings)
    client.append_row(row)
    print(
        "Appended status row to "
        f"spreadsheet={settings.spreadsheet_id}, worksheet={settings.worksheet_name}"
    )
    try_append_operation_log(
        settings=settings,
        operation="app.main",
        result="success",
        purpose="Append starter automation status row.",
        variables={
            "message": args.message,
            "worksheet": settings.worksheet_name,
            "spreadsheet_id": settings.spreadsheet_id,
        },
        details="Status row appended.",
    )


if __name__ == "__main__":
    main()
