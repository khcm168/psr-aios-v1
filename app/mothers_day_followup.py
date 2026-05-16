from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from app.config import _required_env


DEFAULT_SOURCE_WORKBOOK_TITLE = "地區會議資料V7.0 beta"
DEFAULT_TAB_NAME = "母親節追蹤"
DEFAULT_OUTPUT_DIR = Path("data/mothers_day_followup")
DEFAULT_FOCUS_STATUSES = ("追蹤中", "鼓勵自用體驗", "擴量中")
CLOSED_STATUS_TERMS = (
    "已完成",
    "完成",
    "已結案",
    "結案",
    "不追蹤",
    "放棄",
    "暫停",
    "取消",
    "無效",
)

STATUS_HEADER_CANDIDATES = (
    "狀態",
    "狀況",
    "現況",
    "追蹤狀態",
    "跟進狀態",
    "目前狀態",
    "目前狀況",
    "進度",
    "後續狀態",
    "關懷狀態",
    "階段",
)
CUSTOMER_HEADER_CANDIDATES = (
    "客戶名稱",
    "客戶",
    "姓名",
    "診所名稱",
    "院所名稱",
    "藥局名稱",
    "店名",
    "對象",
)
REGION_HEADER_CANDIDATES = (
    "區域",
    "地區",
    "區",
    "業務區碼",
    "區碼",
    "組別",
    "團隊",
    "team",
    "n區",
)
OWNER_HEADER_CANDIDATES = (
    "負責人",
    "業務人員",
    "業務代表",
    "負責業務",
    "擔當",
    "窗口",
    "拜訪人員",
)
EVIDENCE_HEADER_CANDIDATES = (
    "備註",
    "追蹤內容",
    "最新進度",
    "活動回饋",
    "上次拜訪",
    "下一步",
    "紀錄",
)
STATUS_VALUE_TERMS = DEFAULT_FOCUS_STATUSES + CLOSED_STATUS_TERMS + (
    "追蹤",
    "體驗",
    "擴量",
)


@dataclass(frozen=True)
class MothersDayFollowupConfig:
    source_spreadsheet_id: str
    source_workbook_title: str
    tab_name: str
    output_dir: Path
    report_date: str
    region: str
    focus_statuses: tuple[str, ...]
    include_other_open: bool
    max_rows: int

    @classmethod
    def from_env(
        cls,
        *,
        source_spreadsheet_id: str | None = None,
        source_workbook_title: str | None = None,
        tab_name: str | None = None,
        output_dir: str | Path | None = None,
        report_date: str | None = None,
        region: str = "N1",
        focus_statuses: Iterable[str] = DEFAULT_FOCUS_STATUSES,
        include_other_open: bool = False,
        max_rows: int = 0,
    ) -> "MothersDayFollowupConfig":
        return cls(
            source_spreadsheet_id=source_spreadsheet_id
            or os.getenv("N1_SOURCE_SPREADSHEET_ID")
            or os.getenv("GOOGLE_SHEET_ID")
            or os.getenv("SPREADSHEET_ID")
            or _required_env("N1_SOURCE_SPREADSHEET_ID"),
            source_workbook_title=source_workbook_title
            or os.getenv("N1_SOURCE_WORKBOOK_TITLE", DEFAULT_SOURCE_WORKBOOK_TITLE),
            tab_name=tab_name
            or os.getenv("MOTHERS_DAY_FOLLOWUP_TAB", DEFAULT_TAB_NAME),
            output_dir=Path(
                output_dir
                or os.getenv("MOTHERS_DAY_FOLLOWUP_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
            ),
            report_date=report_date or date.today().isoformat(),
            region=region,
            focus_statuses=tuple(status for status in focus_statuses if status),
            include_other_open=include_other_open,
            max_rows=max_rows,
        )


def build_followup_pack(
    *,
    spreadsheet: Any,
    config: MothersDayFollowupConfig,
) -> dict[str, Any]:
    actual_title = getattr(spreadsheet, "title", "")
    worksheet = spreadsheet.worksheet(config.tab_name)
    values = worksheet.get_all_values()
    table = table_from_values(values)
    rows, diagnostics = select_followup_rows(table, config)
    action_rows = [build_action_row(row, table, config) for row in rows]

    return {
        "pack_name": "mothers_day_followup",
        "report_date": config.report_date,
        "source": {
            "spreadsheet_id": config.source_spreadsheet_id,
            "expected_workbook_title": config.source_workbook_title,
            "actual_workbook_title": actual_title,
            "title_matches_expected": (not actual_title)
            or actual_title == config.source_workbook_title,
            "tab": config.tab_name,
            "header_row": table["header_row"],
        },
        "filters": {
            "region": config.region,
            "focus_statuses": list(config.focus_statuses),
            "include_other_open": config.include_other_open,
            "max_rows": config.max_rows,
        },
        "diagnostics": diagnostics,
        "rows": action_rows,
    }


def table_from_values(values: list[list[str]]) -> dict[str, Any]:
    trimmed = [_trim_row(row) for row in values]
    header_index = find_header_index(trimmed)
    if header_index is None:
        return {"headers": [], "records": [], "header_row": 0}

    width = max((len(row) for row in trimmed[header_index:]), default=0)
    raw_headers = trimmed[header_index] + [""] * (width - len(trimmed[header_index]))
    headers = dedupe_headers(raw_headers)
    records = []
    for offset, raw_row in enumerate(trimmed[header_index + 1 :], start=header_index + 2):
        record = row_to_record(headers, raw_row)
        if any(value for value in record.values()):
            records.append({"source_row": offset, "values": record})
    return {"headers": headers, "records": records, "header_row": header_index + 1}


def find_header_index(rows: list[list[str]]) -> int | None:
    best_index = None
    best_score = 0
    for index, row in enumerate(rows[:15]):
        non_empty = [cell for cell in row if cell]
        if len(non_empty) < 2:
            continue
        score = len(non_empty)
        header_hits = 0
        normalized = [normalize_header(cell) for cell in row]
        for candidates in (
            STATUS_HEADER_CANDIDATES,
            CUSTOMER_HEADER_CANDIDATES,
            REGION_HEADER_CANDIDATES,
            OWNER_HEADER_CANDIDATES,
        ):
            if find_header(row, candidates):
                header_hits += 1
                score += 8
        if header_hits:
            score += status_value_score(rows, index)
        if header_hits and any("母親" in cell or "追蹤" in cell for cell in normalized):
            score += 3
        if score > best_score:
            best_index = index
            best_score = score
    return best_index


def select_followup_rows(
    table: dict[str, Any],
    config: MothersDayFollowupConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    headers = table["headers"]
    status_header = resolve_status_header(table, config.focus_statuses)
    region_header = find_header(headers, REGION_HEADER_CANDIDATES)

    if not status_header:
        raise RuntimeError(
            f"Missing status column in {config.tab_name}. Tried: {', '.join(STATUS_HEADER_CANDIDATES)}"
        )

    records = table["records"]
    region_filter_applied = False
    if region_header and config.region:
        region_filter_applied = any(
            config.region.lower() in normalize_text(row["values"].get(region_header, "")).lower()
            for row in records
        )

    selected = []
    for row in records:
        values = row["values"]
        status = normalize_text(values.get(status_header, ""))
        if not is_open_status(status):
            continue
        if region_filter_applied and config.region.lower() not in normalize_text(
            values.get(region_header, "")
        ).lower():
            continue
        if not config.include_other_open and not status_in_focus(
            status, config.focus_statuses
        ):
            continue
        selected.append(row)

    selected.sort(
        key=lambda row: (
            status_priority(normalize_text(row["values"].get(status_header, ""))),
            row["source_row"],
        )
    )
    if config.max_rows > 0:
        selected = selected[: config.max_rows]

    return selected, {
        "source_rows": len(records),
        "selected_rows": len(selected),
        "status_header": status_header,
        "region_header": region_header,
        "region_filter_applied": region_filter_applied,
    }


def build_action_row(
    row: dict[str, Any],
    table: dict[str, Any],
    config: MothersDayFollowupConfig,
) -> dict[str, str | int]:
    values = row["values"]
    status_header = resolve_status_header(table, config.focus_statuses) or ""
    customer_header = find_header(table["headers"], CUSTOMER_HEADER_CANDIDATES) or ""
    owner_header = find_header(table["headers"], OWNER_HEADER_CANDIDATES) or ""
    region_header = find_header(table["headers"], REGION_HEADER_CANDIDATES) or ""
    status = normalize_text(values.get(status_header, ""))
    customer = normalize_text(values.get(customer_header, "")) or "客戶"
    owner = normalize_text(values.get(owner_header, ""))
    region = normalize_text(values.get(region_header, ""))
    classification = classify_status(status)

    return {
        "priority": classification["priority"],
        "sheet_row": row["source_row"],
        "customer": customer,
        "owner": owner,
        "region": region,
        "status": status,
        "status_class": classification["label"],
        "line_text": build_line_text(customer, status),
        "visit_next_step": build_visit_next_step(status),
        "evidence": summarize_evidence(values),
    }


def classify_status(status: str) -> dict[str, str]:
    normalized = normalize_text(status)
    if "擴量" in normalized:
        return {"priority": "P1", "label": "擴量推進"}
    if "自用" in normalized or "體驗" in normalized:
        return {"priority": "P1", "label": "自用體驗轉換"}
    if "追蹤" in normalized:
        return {"priority": "P2", "label": "需求確認追蹤"}
    return {"priority": "P3", "label": "其他開放追蹤"}


def build_line_text(customer: str, status: str) -> str:
    name = normalize_customer_name(customer)
    normalized = normalize_text(status)
    if "擴量" in normalized:
        text = (
            f"{name}您好，母親節活動後想協助確認目前用量與補貨節奏，避免需求起來時斷點。"
            "這週方便我過去快速對一下嗎？"
        )
    elif "自用" in normalized or "體驗" in normalized:
        text = (
            f"{name}您好，母親節活動後想先邀請您做自用體驗，感受用法與回饋。"
            "我可以帶重點說明，找10分鐘跟您對一下。"
        )
    else:
        text = (
            f"{name}您好，母親節活動後想跟您確認目前回饋與需求；若方便，"
            "我這週找10分鐘聽您的想法，再一起看下一步。"
        )
    return compact_text(text, 120)


def build_visit_next_step(status: str) -> str:
    normalized = normalize_text(status)
    if "擴量" in normalized:
        return (
            "先核對現有庫存、近兩週消耗與可接受補貨量；拜訪時帶一個保守補量與一個活動延伸組合，"
            "當場確認決策人、下單時點與是否需要搭配陳列/衛教素材。"
        )
    if "自用" in normalized or "體驗" in normalized:
        return (
            "帶小份體驗品或用法重點，先降低嘗試門檻；拜訪時約定明確回饋日，確認使用情境、接受度與疑慮，"
            "回饋良好就推進到首批採購或內部試用名單。"
        )
    if "追蹤" in normalized:
        return (
            "先查最後一次互動與未解問題；拜訪時只確認三件事：活動後是否仍有需求、目前卡點、可接受的下一步。"
            "結束前留下具體日期與下一個動作。"
        )
    return (
        "資料顯示仍需追蹤；先人工確認最近一次互動內容，再用低壓方式約短訪，補齊需求、疑慮、下一步日期。"
    )


def render_markdown(pack: dict[str, Any]) -> str:
    lines = [
        f"# 母親節追蹤 N1 行動清單 {pack['report_date']}",
        "",
        f"- Source workbook: {pack['source']['actual_workbook_title'] or pack['source']['expected_workbook_title']}",
        f"- Source tab: {pack['source']['tab']} (header row {pack['source']['header_row']})",
        f"- Rows selected: {pack['diagnostics']['selected_rows']} of {pack['diagnostics']['source_rows']}",
        f"- Focus statuses: {', '.join(pack['filters']['focus_statuses'])}",
    ]
    if not pack["diagnostics"].get("region_filter_applied"):
        lines.append("- Region filter: not applied because no matching N1 region column values were found")
    if not pack["source"]["title_matches_expected"]:
        lines.append(
            f"- Warning: expected workbook title `{pack['source']['expected_workbook_title']}`"
        )
    lines.append("")

    if not pack["rows"]:
        lines.append("_No matching open follow-up rows found._")
        return "\n".join(lines).rstrip() + "\n"

    headers = [
        "Priority",
        "Row",
        "Customer",
        "Owner",
        "Region",
        "Status",
        "Class",
        "LINE",
        "Visit next step",
        "Evidence",
    ]
    lines.append(markdown_row(headers))
    lines.append(markdown_row(["---"] * len(headers)))
    for row in pack["rows"]:
        lines.append(
            markdown_row(
                [
                    row["priority"],
                    row["sheet_row"],
                    row["customer"],
                    row["owner"],
                    row["region"],
                    row["status"],
                    row["status_class"],
                    row["line_text"],
                    row["visit_next_step"],
                    row["evidence"],
                ]
            )
        )
    return "\n".join(lines).rstrip() + "\n"


def write_followup_pack(
    pack: dict[str, Any],
    output_dir: Path,
    report_date: str,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"mothers_day_followup_{report_date}"
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
        prog="mothers_day_followup",
        description="Build an actionable N1 Mother’s Day follow-up pack from Google Sheets.",
    )
    parser.add_argument("--date", dest="report_date")
    parser.add_argument("--source-spreadsheet-id")
    parser.add_argument("--source-workbook-title")
    parser.add_argument("--tab", default=None)
    parser.add_argument("--output-dir")
    parser.add_argument("--region", default="N1")
    parser.add_argument(
        "--status",
        action="append",
        dest="focus_statuses",
        help="Open status to include. Repeat to override defaults.",
    )
    parser.add_argument(
        "--include-other-open",
        action="store_true",
        help="Include open statuses beyond the focused campaign statuses.",
    )
    parser.add_argument(
        "--debug-headers",
        action="store_true",
        help="Print detected headers and the first non-empty rows without writing output files.",
    )
    parser.add_argument("--max-rows", type=int, default=0)
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
    config = MothersDayFollowupConfig.from_env(
        source_spreadsheet_id=args.source_spreadsheet_id,
        source_workbook_title=args.source_workbook_title,
        tab_name=args.tab,
        output_dir=args.output_dir,
        report_date=args.report_date,
        region=args.region,
        focus_statuses=args.focus_statuses or DEFAULT_FOCUS_STATUSES,
        include_other_open=args.include_other_open,
        max_rows=args.max_rows,
    )
    settings = Settings.from_env(require_google=True)

    try:
        spreadsheet = GoogleApiSpreadsheet.from_credentials(
            credentials_path=settings.google_credentials_path,
            spreadsheet_id=config.source_spreadsheet_id,
        )
        if args.debug_headers:
            values = spreadsheet.worksheet(config.tab_name).get_all_values()
            table = table_from_values(values)
            debug_rows = [row for row in values if any(str(cell).strip() for cell in row)][:12]
            print(
                json.dumps(
                    {
                        "tab": config.tab_name,
                        "detected_header_row": table["header_row"],
                        "detected_headers": table["headers"],
                        "first_non_empty_rows": debug_rows,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
        pack = build_followup_pack(spreadsheet=spreadsheet, config=config)
        markdown_path, json_path = write_followup_pack(
            pack, config.output_dir, config.report_date
        )
        sync_context = build_file_sync_context([markdown_path, json_path])
        print(f"Wrote {markdown_path}")
        print(f"Wrote {json_path}")
        print(
            "Selected "
            f"{pack['diagnostics']['selected_rows']} of {pack['diagnostics']['source_rows']} rows."
        )
        try_append_operation_log(
            settings=settings,
            operation="mothers_day_followup",
            result="success",
            purpose="Build actionable N1 Mother’s Day follow-up LINE and visit next-step pack.",
            variables={
                "source_spreadsheet_id": config.source_spreadsheet_id,
                "tab": config.tab_name,
                "report_date": config.report_date,
                "region": config.region,
                "focus_statuses": list(config.focus_statuses),
                "include_other_open": config.include_other_open,
                "selected_rows": pack["diagnostics"]["selected_rows"],
                "markdown_path": str(markdown_path),
                "json_path": str(json_path),
                "markdown_abs_path": str(markdown_path.resolve()),
                "json_abs_path": str(json_path.resolve()),
                "file_sync": sync_context,
            },
            details=build_result_link_details(
                message="Mother's Day follow-up pack files written.",
                result_path=markdown_path,
                sync_context=sync_context,
            ),
        )
    except Exception as exc:
        try_append_operation_log(
            settings=settings,
            operation="mothers_day_followup",
            result="failure",
            purpose="Build actionable N1 Mother’s Day follow-up LINE and visit next-step pack.",
            variables={
                "source_spreadsheet_id": config.source_spreadsheet_id,
                "tab": config.tab_name,
                "report_date": config.report_date,
                "region": config.region,
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
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Google Sheets dependencies are missing. Run `pip install -r requirements.txt`."
            ) from exc
        except ImportError as exc:
            raise RuntimeError(f"Google Sheets dependencies failed to import: {exc}") from exc

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
            range=f"{quote_sheet_name(self.name)}!A:ZZ",
        ).execute()
        return result.get("values", [])


def status_priority(status: str) -> int:
    normalized = normalize_text(status)
    if "擴量" in normalized:
        return 1
    if "自用" in normalized or "體驗" in normalized:
        return 2
    if "追蹤" in normalized:
        return 3
    return 9


def resolve_status_header(
    table: dict[str, Any],
    focus_statuses: Iterable[str],
) -> str | None:
    return find_header(table["headers"], STATUS_HEADER_CANDIDATES) or infer_status_header(
        table, focus_statuses
    )


def infer_status_header(
    table: dict[str, Any],
    focus_statuses: Iterable[str],
) -> str | None:
    terms = tuple(focus_statuses) + STATUS_VALUE_TERMS
    best_header = None
    best_score = 0
    for header in table["headers"]:
        score = 0
        for row in table["records"]:
            value = normalize_text(row["values"].get(header, ""))
            if any(normalize_text(term) in value for term in terms):
                score += 1
        if score > best_score:
            best_header = header
            best_score = score
    return best_header if best_score > 0 else None


def status_value_score(rows: list[list[str]], header_index: int) -> int:
    score = 0
    for row in rows[header_index + 1 : header_index + 21]:
        for cell in row:
            value = normalize_text(cell)
            if any(normalize_text(term) in value for term in STATUS_VALUE_TERMS):
                score += 4
                break
    return min(score, 20)


def status_in_focus(status: str, focus_statuses: Iterable[str]) -> bool:
    normalized = normalize_text(status)
    for term in focus_statuses:
        target = normalize_text(term)
        if target in normalized:
            return True
        if ("自用" in target or "體驗" in target) and (
            "自用" in normalized or "體驗" in normalized
        ):
            return True
        if "擴量" in target and "擴量" in normalized:
            return True
        if "追蹤" in target and "追蹤" in normalized:
            return True
    return False


def is_open_status(status: str) -> bool:
    normalized = normalize_text(status)
    if not normalized:
        return False
    return not any(term in normalized for term in CLOSED_STATUS_TERMS)


def summarize_evidence(values: dict[str, str]) -> str:
    chunks = []
    for header, value in values.items():
        if not value:
            continue
        if header_matches(header, EVIDENCE_HEADER_CANDIDATES):
            chunks.append(f"{header}: {compact_text(value, 70)}")
    if not chunks:
        for header, value in values.items():
            if value and not header_matches(header, STATUS_HEADER_CANDIDATES):
                chunks.append(f"{header}: {compact_text(value, 45)}")
            if len(chunks) >= 2:
                break
    return compact_text(" / ".join(chunks), 180)


def find_header(headers: list[str], candidates: Iterable[str]) -> str | None:
    for header in headers:
        if header_matches(header, candidates, exact=True):
            return header
    for header in headers:
        if header_matches(header, candidates):
            return header
    return None


def header_matches(header: str, candidates: Iterable[str], exact: bool = False) -> bool:
    normalized = normalize_header(header)
    for candidate in candidates:
        target = normalize_header(candidate)
        if exact and normalized == target:
            return True
        if not exact and (target in normalized or normalized in target):
            return True
    return False


def row_to_record(headers: list[str], row: list[str]) -> dict[str, str]:
    padded = row + [""] * (len(headers) - len(row))
    return dict(zip(headers, padded[: len(headers)]))


def dedupe_headers(headers: list[str]) -> list[str]:
    result = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers):
        name = header or f"column_{index + 1}"
        seen[name] = seen.get(name, 0) + 1
        result.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return result


def normalize_customer_name(customer: str) -> str:
    name = normalize_text(customer)
    if not name or name == "客戶":
        return "您好"
    return name


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", "\n")
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def normalize_header(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").replace("\r", " ").replace("\n", " ")).strip().lower()


def compact_text(text: Any, max_len: int) -> str:
    normalized = normalize_text(text)
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max(0, max_len - 1)].rstrip() + "…"


def _trim_row(row: list[str]) -> list[str]:
    return [normalize_text(cell) for cell in row]


def markdown_row(values: list[Any]) -> str:
    escaped = [
        str(value).replace("|", "\\|").replace("\n", " ")
        for value in values
    ]
    return "| " + " | ".join(escaped) + " |"


def quote_sheet_name(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


if __name__ == "__main__":
    main()
