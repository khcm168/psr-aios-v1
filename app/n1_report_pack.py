from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from app.config import _required_env


DEFAULT_SOURCE_WORKBOOK_TITLE = "地區會議資料V7.0 beta"
DEFAULT_TABS = (
    "Action Plan 進度",
    "本月行動計畫",
    "今日拜訪",
    "反映事項",
)


def default_report_date(today: date | None = None) -> str:
    """Return the next Monday on or after today for the N1 report cycle."""
    base_date = today or date.today()
    days_until_monday = (0 - base_date.weekday()) % 7
    return (base_date + timedelta(days=days_until_monday)).isoformat()


@dataclass(frozen=True)
class ReportPackConfig:
    source_spreadsheet_id: str
    source_workbook_title: str
    weekly_report_spreadsheet_id: str
    operations_report_spreadsheet_id: str
    report_date: str
    output_dir: Path
    tabs: tuple[str, ...]
    max_rows_per_section: int

    @classmethod
    def from_env(
        cls,
        *,
        source_spreadsheet_id: str | None = None,
        source_workbook_title: str | None = None,
        weekly_report_spreadsheet_id: str | None = None,
        operations_report_spreadsheet_id: str | None = None,
        report_date: str | None = None,
        output_dir: str | Path | None = None,
        tabs: Iterable[str] = DEFAULT_TABS,
        max_rows_per_section: int = 12,
    ) -> "ReportPackConfig":
        return cls(
            source_spreadsheet_id=source_spreadsheet_id
            or os.getenv("N1_SOURCE_SPREADSHEET_ID")
            or os.getenv("GOOGLE_SHEET_ID")
            or os.getenv("SPREADSHEET_ID")
            or _required_env("N1_SOURCE_SPREADSHEET_ID"),
            source_workbook_title=source_workbook_title
            or os.getenv("N1_SOURCE_WORKBOOK_TITLE", DEFAULT_SOURCE_WORKBOOK_TITLE),
            weekly_report_spreadsheet_id=weekly_report_spreadsheet_id
            or os.getenv("N1_WEEKLY_REPORT_SPREADSHEET_ID", ""),
            operations_report_spreadsheet_id=operations_report_spreadsheet_id
            or os.getenv("N1_OPERATIONS_REPORT_SPREADSHEET_ID", ""),
            report_date=report_date
            or os.getenv("N1_REPORT_DATE")
            or default_report_date(),
            output_dir=Path(
                output_dir
                or os.getenv("N1_REPORT_PACK_OUTPUT_DIR", "data/report_packs")
            ),
            tabs=tuple(tabs),
            max_rows_per_section=max_rows_per_section,
        )


def build_report_pack(
    *,
    spreadsheet: Any,
    config: ReportPackConfig,
) -> dict[str, Any]:
    actual_title = getattr(spreadsheet, "title", "")
    sections = []
    for tab_name in config.tabs:
        try:
            worksheet = spreadsheet.worksheet(tab_name)
            values = worksheet.get_all_values()
            section = section_from_values(tab_name, values, config.max_rows_per_section)
        except Exception as exc:
            section = {
                "tab": tab_name,
                "status": "missing",
                "headers": [],
                "rows": [],
                "note": str(exc),
            }
        sections.append(section)

    return {
        "pack_name": "n1_report_pack",
        "source": {
            "spreadsheet_id": config.source_spreadsheet_id,
            "expected_workbook_title": config.source_workbook_title,
            "actual_workbook_title": actual_title,
            "title_matches_expected": (not actual_title)
            or actual_title == config.source_workbook_title,
        },
        "reports": [
            {
                "title": f"N1 週報 {config.report_date}",
                "spreadsheet_id": config.weekly_report_spreadsheet_id,
            },
            {
                "title": f"N1 地區業績營運報告 {config.report_date}",
                "spreadsheet_id": config.operations_report_spreadsheet_id,
            },
        ],
        "sections": sections,
    }


def section_from_values(
    tab_name: str,
    values: list[list[str]],
    max_rows: int,
) -> dict[str, Any]:
    normalized = [_trim_row(row) for row in values]
    normalized = [row for row in normalized if any(cell for cell in row)]
    if not normalized:
        return {"tab": tab_name, "status": "empty", "headers": [], "rows": []}

    header_index = _find_header_index(normalized)
    headers = _dedupe_headers(normalized[header_index])
    rows = []
    for raw_row in normalized[header_index + 1 :]:
        row = _row_to_record(headers, raw_row)
        if any(value for value in row.values()):
            rows.append(row)
        if len(rows) >= max_rows:
            break

    return {
        "tab": tab_name,
        "status": "ok",
        "headers": headers,
        "rows": rows,
        "source_row_count": max(0, len(normalized) - header_index - 1),
    }


def render_markdown(pack: dict[str, Any]) -> str:
    lines = [
        f"# {pack['reports'][0]['title']} / {pack['reports'][1]['title']}",
        "",
        f"- Source workbook: {pack['source']['actual_workbook_title'] or pack['source']['expected_workbook_title']}",
        f"- Source spreadsheet ID: `{pack['source']['spreadsheet_id']}`",
    ]
    if not pack["source"]["title_matches_expected"]:
        lines.append(
            f"- Warning: expected workbook title `{pack['source']['expected_workbook_title']}`"
        )
    lines.append("")

    for section in pack["sections"]:
        lines.extend(_render_section(section))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_report_pack(pack: dict[str, Any], output_dir: Path, report_date: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"n1_report_pack_{report_date}"
    markdown_path = output_dir / f"{stem}.md"
    json_path = output_dir / f"{stem}.json"
    markdown_path.write_text(render_markdown(pack), encoding="utf-8")
    json_path.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return markdown_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="n1_report_pack",
        description="Build the N1 weekly and operations report source pack from Google Sheets.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Report date (YYYY-MM-DD). Defaults to the next Monday on or after today.",
    )
    parser.add_argument("--output-dir")
    parser.add_argument("--source-spreadsheet-id")
    parser.add_argument("--source-workbook-title")
    parser.add_argument("--weekly-report-spreadsheet-id")
    parser.add_argument("--operations-report-spreadsheet-id")
    parser.add_argument("--tab", action="append", dest="tabs")
    parser.add_argument("--max-rows-per-section", type=int, default=12)
    return parser.parse_args()


def main() -> None:
    from app.config import Settings, load_environment
    from app.operation_log import (
        build_file_sync_context,
        build_result_link_details,
        try_append_operation_log,
    )

    load_environment()
    args = parse_args()
    config = ReportPackConfig.from_env(
        source_spreadsheet_id=args.source_spreadsheet_id,
        source_workbook_title=args.source_workbook_title,
        weekly_report_spreadsheet_id=args.weekly_report_spreadsheet_id,
        operations_report_spreadsheet_id=args.operations_report_spreadsheet_id,
        report_date=args.date,
        output_dir=args.output_dir,
        tabs=args.tabs or DEFAULT_TABS,
        max_rows_per_section=args.max_rows_per_section,
    )
    _validate_date(config.report_date)
    settings = Settings.from_env(require_google=True)
    try:
        spreadsheet = GoogleApiSpreadsheet.from_credentials(
            credentials_path=settings.google_credentials_path,
            spreadsheet_id=config.source_spreadsheet_id,
        )

        pack = build_report_pack(spreadsheet=spreadsheet, config=config)
        markdown_path, json_path = write_report_pack(
            pack, config.output_dir, config.report_date
        )
        sync_context = build_file_sync_context([markdown_path, json_path])
        print(f"Wrote {markdown_path}")
        print(f"Wrote {json_path}")
        try_append_operation_log(
            settings=settings,
            operation="n1_report_pack",
            result="success",
            purpose="Build N1 weekly and operations report source pack from Google Sheets.",
            variables={
                "source_spreadsheet_id": config.source_spreadsheet_id,
                "report_date": config.report_date,
                "tabs": list(config.tabs),
                "max_rows_per_section": config.max_rows_per_section,
                "markdown_path": str(markdown_path),
                "json_path": str(json_path),
                "markdown_abs_path": str(markdown_path.resolve()),
                "json_abs_path": str(json_path.resolve()),
                "file_sync": sync_context,
            },
            details=build_result_link_details(
                message="Report pack files written.",
                result_path=markdown_path,
                sync_context=sync_context,
            ),
        )
    except Exception as exc:
        try_append_operation_log(
            settings=settings,
            operation="n1_report_pack",
            result="failure",
            purpose="Build N1 weekly and operations report source pack from Google Sheets.",
            variables={
                "source_spreadsheet_id": config.source_spreadsheet_id,
                "report_date": config.report_date,
                "tabs": list(config.tabs),
                "max_rows_per_section": config.max_rows_per_section,
            },
            details=str(exc),
        )
        raise


class GoogleApiSpreadsheet:
    def __init__(self, service: Any, spreadsheet_id: str, title: str) -> None:
        self.service = service
        self.spreadsheet_id = spreadsheet_id
        self.title = title

    @classmethod
    def from_credentials(
        cls,
        *,
        credentials_path: Path,
        spreadsheet_id: str,
    ) -> "GoogleApiSpreadsheet":
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except (ImportError, ModuleNotFoundError) as exc:
            raise RuntimeError(
                "Google Sheets dependencies are missing. Run `pip install -r requirements.txt`."
            ) from exc

        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        service = build("sheets", "v4", credentials=credentials)
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        title = metadata.get("properties", {}).get("title", "")
        return cls(service=service, spreadsheet_id=spreadsheet_id, title=title)

    def worksheet(self, name: str) -> "GoogleApiWorksheet":
        return GoogleApiWorksheet(self.service, self.spreadsheet_id, name)


class GoogleApiWorksheet:
    def __init__(self, service: Any, spreadsheet_id: str, name: str) -> None:
        self.service = service
        self.spreadsheet_id = spreadsheet_id
        self.name = name

    def get_all_values(self) -> list[list[str]]:
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{_quote_sheet_name(self.name)}!A:ZZ",
        ).execute()
        return result.get("values", [])


def _render_section(section: dict[str, Any]) -> list[str]:
    lines = [f"## {section['tab']}"]
    if section["status"] != "ok":
        note = section.get("note", section["status"])
        return lines + [f"_No rows included: {note}_"]
    if not section["rows"]:
        return lines + ["_No rows found._"]

    headers = section["headers"]
    lines.append(_markdown_row(headers))
    lines.append(_markdown_row(["---"] * len(headers)))
    for row in section["rows"]:
        lines.append(_markdown_row([row.get(header, "") for header in headers]))
    if section.get("source_row_count", 0) > len(section["rows"]):
        lines.append("")
        lines.append(
            f"_Showing {len(section['rows'])} of {section['source_row_count']} source rows._"
        )
    return lines


def _find_header_index(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows[:10]):
        non_empty = [cell for cell in row if cell]
        if len(non_empty) >= 2:
            return index
    return 0


def _trim_row(row: list[str]) -> list[str]:
    return [str(cell).strip() for cell in row]


def _dedupe_headers(headers: list[str]) -> list[str]:
    result = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers):
        name = header or f"column_{index + 1}"
        seen[name] = seen.get(name, 0) + 1
        result.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return result


def _row_to_record(headers: list[str], row: list[str]) -> dict[str, str]:
    padded = row + [""] * (len(headers) - len(row))
    return dict(zip(headers, padded[: len(headers)]))


def _markdown_row(values: list[str]) -> str:
    escaped = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
    return "| " + " | ".join(escaped) + " |"


def _validate_date(value: str) -> None:
    date.fromisoformat(value)


def _quote_sheet_name(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


if __name__ == "__main__":
    main()
