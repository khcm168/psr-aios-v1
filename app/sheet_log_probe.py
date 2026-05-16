from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Sequence

from app.config import Settings
from app.operation_log import append_operation_log, build_operation_row


def build_probe_row(
    *,
    project_name: str,
    message: str,
    status: str = "ok",
    timestamp: datetime | None = None,
) -> list[str]:
    occurred_at = timestamp or datetime.now(timezone.utc)
    return build_operation_row(
        project_name=project_name,
        operation="sheet-log-probe",
        result=status,
        purpose="Verify real Google Sheets append/readback access.",
        variables={"message": message},
        details=message,
        timestamp=occurred_at,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append a Google Sheets log row to prove real write access works."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the row that would be appended without calling Google Sheets.",
    )
    parser.add_argument(
        "--message",
        default="Real Google Sheets append probe from psr-aios-v1",
        help="Message to include in the log row.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read the worksheet after appending and print the final row.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    settings = Settings.from_env(require_google=not args.dry_run)
    row = build_probe_row(project_name=settings.project_name, message=args.message)

    if args.dry_run:
        print(f"Dry run sheet log row: {row}")
        return

    append_operation_log(
        settings=settings,
        operation="sheet-log-probe",
        result="ok",
        purpose="Verify real Google Sheets append/readback access.",
        variables={"message": args.message},
        details=args.message,
        verify=args.verify,
    )
    print(
        "Appended sheet log probe row to "
        f"spreadsheet={settings.spreadsheet_id}, worksheet={settings.worksheet_name}"
    )
    if args.verify:
        from app.operation_log import read_last_operation_log_row

        last_row = read_last_operation_log_row(settings=settings)
        print(f"Verified last sheet row: {last_row}")
    print("Operation log row includes time, purpose, result, and variables_json.")


if __name__ == "__main__":
    main()
