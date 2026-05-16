from __future__ import annotations

import getpass
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings


LOG_HEADER = [
    "occurred_at",
    "project",
    "operation",
    "result",
    "purpose",
    "variables_json",
    "details",
    "host",
    "user",
]


def build_operation_row(
    *,
    project_name: str,
    operation: str,
    result: str,
    purpose: str,
    variables: dict[str, Any] | None = None,
    details: str = "",
    timestamp: datetime | None = None,
) -> list[str]:
    occurred_at = timestamp or datetime.now(timezone.utc)
    return [
        occurred_at.isoformat(),
        project_name,
        operation,
        result,
        purpose,
        json.dumps(variables or {}, ensure_ascii=False, sort_keys=True),
        details,
        platform.node(),
        getpass.getuser(),
    ]


def append_operation_log(
    *,
    settings: Settings,
    operation: str,
    result: str,
    purpose: str,
    variables: dict[str, Any] | None = None,
    details: str = "",
    verify: bool = False,
) -> list[str]:
    from app.sheets import GoogleSheetsClient

    client = GoogleSheetsClient.from_settings(settings)
    client.ensure_header(LOG_HEADER)
    row = build_operation_row(
        project_name=settings.project_name,
        operation=operation,
        result=result,
        purpose=purpose,
        variables=variables,
        details=details,
    )
    client.append_row(row)
    if verify:
        last_row = read_last_operation_log_row(settings=settings, client=client)
        if not operation_log_row_matches(row, last_row):
            raise RuntimeError(
                "Operation log verification failed: appended row was not the last row."
            )
    return row


def try_append_operation_log(
    *,
    settings: Settings | None = None,
    operation: str,
    result: str,
    purpose: str,
    variables: dict[str, Any] | None = None,
    details: str = "",
    verify: bool = False,
) -> bool:
    try:
        append_operation_log(
            settings=settings or Settings.from_env(require_google=True),
            operation=operation,
            result=result,
            purpose=purpose,
            variables=variables,
            details=details,
            verify=verify,
        )
        return True
    except Exception as exc:
        print(f"WARNING: failed to append operation log: {exc}")
        return False


def read_last_operation_log_row(
    *,
    settings: Settings,
    client: Any | None = None,
) -> list[str]:
    if client is None:
        from app.sheets import GoogleSheetsClient

        client = GoogleSheetsClient.from_settings(settings)
    values = client.worksheet_values(settings.worksheet_name)
    return values[-1] if values else []


def operation_log_row_matches(expected: list[str], actual: list[str]) -> bool:
    return actual[: len(expected)] == expected


def build_result_link_details(
    *,
    message: str,
    result_path: str | Path,
    sync_context: dict[str, Any] | None = None,
) -> str:
    path = Path(result_path).resolve()
    label = f"{message} Open result"
    if sync_context and sync_context.get("provider"):
        label += f" ({sync_context['provider']} local sync)"
    return f'=HYPERLINK("{_file_uri(path)}","{_formula_text(label)}")'


def build_file_sync_context(paths: list[str | Path]) -> dict[str, Any]:
    resolved_paths = [Path(path).resolve() for path in paths]
    first_existing_parent = next(
        (path.parent for path in resolved_paths if path.exists()),
        resolved_paths[0].parent if resolved_paths else Path.cwd(),
    )
    provider = ""
    sync_root = ""
    for parent in [first_existing_parent, *first_existing_parent.parents]:
        if "onedrive" in parent.name.lower():
            provider = "OneDrive"
            sync_root = str(parent)
            break

    return {
        "provider": provider,
        "local_sync_root": sync_root,
        "absolute_paths": [str(path) for path in resolved_paths],
        "exists": {str(path): path.exists() for path in resolved_paths},
        "note": (
            "Links target local OneDrive-synced files; wait for OneDrive sync before opening from another device."
            if provider == "OneDrive"
            else "Links target local files on this machine."
        ),
    }


def _file_uri(path: Path) -> str:
    return path.as_uri().replace('"', '""')


def _formula_text(value: str) -> str:
    return value.replace('"', '""')
