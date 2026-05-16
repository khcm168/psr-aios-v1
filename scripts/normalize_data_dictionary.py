from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.operation_log import LOG_HEADER, build_operation_row

load_dotenv(ROOT_DIR / ".env")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DICT_SHEET = "Data_Dictionary"
LIST_SHEET = "List"
LOG_SHEET = "log"
DICT_SCAN_RANGE = f"{DICT_SHEET}!A:ZZ"
LIST_HEADER_RANGE = f"{LIST_SHEET}!2:2"

DICT_HEADER = ["sheet", "中文欄名", "internal_key", "type", "role", "note", "write_policy"]

SECOND_KEYMAN_HEADER = "第二Key man(藥師)、電話(Line)、生日、重要事項\n(有多位聯絡人請分別填寫)"

INTERNAL_KEY_RENAMES = {
    "clinic_code": "customer_id",
    "Line Tout": "line_talk_script",
    "line tout": "line_talk_script",
    "Vist_Strategy": "visit_strategy",
    "vist_strategy": "visit_strategy",
    "NEXT_Step": "next_step",
    "next_step": "next_step",
    "calcPriority": "calc_priority",
    "calcpriority": "calc_priority",
    "placeId": "google_place_id",
    "placeid": "google_place_id",
    "business_hours_Updated": "business_hours_updated_at",
    "business_hours_updated": "business_hours_updated_at",
    "proposed_LINE": "proposed_line",
    "proposed_line": "proposed_line",
}

WRITE_POLICY_OVERRIDES = {
    "google_place_id": "script",
    "business_hours_updated_at": "script",
    "line_talk_script": "ai",
    "visit_strategy": "ai",
}


def required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def get_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(required_env("SERVICE_ACCOUNT_FILE"), scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_values(service, range_name: str) -> list[list[str]]:
    result = service.spreadsheets().values().get(
        spreadsheetId=required_env("SPREADSHEET_ID"),
        range=range_name,
    ).execute()
    return result.get("values", [])


def update_values(service, range_name: str, values: list[list[str]]) -> None:
    service.spreadsheets().values().update(
        spreadsheetId=required_env("SPREADSHEET_ID"),
        range=range_name,
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def append_values(service, range_name: str, values: list[list[str]]) -> None:
    service.spreadsheets().values().append(
        spreadsheetId=required_env("SPREADSHEET_ID"),
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


def get_sheet_id_by_name(service, sheet_name: str) -> int | None:
    metadata = service.spreadsheets().get(spreadsheetId=required_env("SPREADSHEET_ID")).execute()
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == sheet_name:
            return props.get("sheetId")
    return None


def ensure_sheet_exists(service, sheet_name: str) -> None:
    if get_sheet_id_by_name(service, sheet_name) is not None:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=required_env("SPREADSHEET_ID"),
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
    ).execute()


def normalize_visible_header(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").replace('"', "")
    return re.sub(r"\s+", "", text).strip()


def normalize_key(value: Any) -> str:
    return str(value or "").strip()


def canonical_key(value: Any) -> str:
    key = normalize_key(value)
    return INTERNAL_KEY_RENAMES.get(key, INTERNAL_KEY_RENAMES.get(key.lower(), key))


def infer_write_policy(field_type: str, role: str, internal_key: str) -> str:
    role_key = str(role or "").strip().lower()
    type_key = str(field_type or "").strip().lower()
    internal = str(internal_key or "").strip().lower()

    if internal.startswith("ai_") or internal in {"line_talk_script", "visit_strategy"}:
        return "ai"
    if role_key == "action":
        return "script"
    if role_key in {"metric", "derived", "primary_key", "foreign_key", "primary_time"}:
        return "readonly"
    if type_key in {"formula", "computed"}:
        return "readonly"
    return "manual"


def col_to_letter(col_num_1_based: int) -> str:
    result = ""
    while col_num_1_based > 0:
        col_num_1_based, remainder = divmod(col_num_1_based - 1, 26)
        result = chr(65 + remainder) + result
    return result


def find_dictionary_table(values: list[list[str]]) -> tuple[int, int, list[list[str]]]:
    expected = [normalize_visible_header(header).lower() for header in DICT_HEADER]
    for row_idx, row in enumerate(values):
        padded = row + [""] * (len(expected) - len(row))
        for col_idx in range(max(len(padded) - len(expected) + 1, 0)):
            candidate = [
                normalize_visible_header(value).lower()
                for value in padded[col_idx : col_idx + len(expected)]
            ]
            if candidate == expected:
                sliced = [
                    (source_row + [""] * (col_idx + len(expected)))[
                        col_idx : col_idx + len(expected)
                    ]
                    for source_row in values[row_idx:]
                ]
                return row_idx + 1, col_idx + 1, sliced
    raise RuntimeError(
        "Could not find Data_Dictionary table headers in "
        f"{DICT_SCAN_RANGE}: {', '.join(DICT_HEADER)}"
    )


def load_dictionary_table(service) -> tuple[list[list[str]], int, int]:
    values = get_values(service, DICT_SCAN_RANGE)
    if not values:
        raise RuntimeError(f"{DICT_SCAN_RANGE} is empty")
    header_row, start_col, sliced_values = find_dictionary_table(values)
    return sliced_values, header_row, start_col


def append_log(service, variables: dict[str, Any], details: str) -> None:
    ensure_sheet_exists(service, LOG_SHEET)
    existing = get_values(service, f"{LOG_SHEET}!A1:I2")
    if not existing or existing[0][: len(LOG_HEADER)] != LOG_HEADER:
        update_values(service, f"{LOG_SHEET}!A1:I1", [LOG_HEADER])
    row = build_operation_row(
        project_name=os.getenv("PROJECT_NAME", "psr-aios-v1"),
        operation="normalize_data_dictionary",
        result="success",
        purpose="Normalize Data_Dictionary keys, add write_policy, and clean List header",
        variables=variables,
        details=details,
    )
    append_values(service, f"{LOG_SHEET}!A:I", [row])


def normalize_dictionary_rows(values: list[list[str]]) -> tuple[list[list[str]], dict[str, Any]]:
    rows = [DICT_HEADER]
    counters: dict[str, Any] = {
        "rows_seen": max(len(values) - 1, 0),
        "keys_renamed": {},
        "headers_cleaned": 0,
        "write_policy_overridden": {},
        "write_policy_filled": 0,
        "write_policy_existing": 0,
    }

    for raw in values[1:]:
        row = raw + [""] * (7 - len(raw))
        row = row[:7]

        old_header = str(row[1] or "")
        if normalize_visible_header(old_header) == normalize_visible_header(SECOND_KEYMAN_HEADER):
            if old_header != SECOND_KEYMAN_HEADER:
                counters["headers_cleaned"] += 1
            row[1] = SECOND_KEYMAN_HEADER

        old_key = normalize_key(row[2])
        new_key = canonical_key(old_key)
        if old_key != new_key:
            counters["keys_renamed"][old_key] = new_key
            row[2] = new_key

        override_policy = WRITE_POLICY_OVERRIDES.get(str(row[2] or "").strip())
        if override_policy:
            if str(row[6] or "").strip() != override_policy:
                counters["write_policy_overridden"][str(row[2])] = override_policy
            row[6] = override_policy
        elif str(row[6] or "").strip():
            counters["write_policy_existing"] += 1
        else:
            row[6] = infer_write_policy(row[3], row[4], row[2])
            counters["write_policy_filled"] += 1

        rows.append(row)

    return rows, counters


def clean_list_second_keyman_header(service) -> dict[str, Any]:
    headers = get_values(service, LIST_HEADER_RANGE)
    if not headers:
        return {"list_header_cleaned": False, "list_header_column": None, "reason": "List row 2 is empty"}

    target_norm = normalize_visible_header(SECOND_KEYMAN_HEADER)
    for index, header in enumerate(headers[0], start=1):
        if normalize_visible_header(header) == target_norm:
            letter = col_to_letter(index)
            if header != SECOND_KEYMAN_HEADER:
                update_values(service, f"{LIST_SHEET}!{letter}2", [[SECOND_KEYMAN_HEADER]])
                return {"list_header_cleaned": True, "list_header_column": letter}
            return {"list_header_cleaned": False, "list_header_column": letter, "reason": "already clean"}

    return {"list_header_cleaned": False, "list_header_column": None, "reason": "header not found"}


def main() -> None:
    service = get_service()
    values, dict_header_row, dict_start_col = load_dictionary_table(service)

    normalized_rows, counters = normalize_dictionary_rows(values)
    dict_start_letter = col_to_letter(dict_start_col)
    dict_end_letter = col_to_letter(dict_start_col + len(DICT_HEADER) - 1)
    dict_end_row = dict_header_row + len(normalized_rows) - 1
    dict_write_range = (
        f"{DICT_SHEET}!{dict_start_letter}{dict_header_row}:{dict_end_letter}{dict_end_row}"
    )
    update_values(service, dict_write_range, normalized_rows)
    list_header_result = clean_list_second_keyman_header(service)

    variables = counters | list_header_result | {
        "dict_range": dict_write_range,
        "write_policy_values": ["manual", "script", "ai", "readonly"],
    }
    details = "Normalized Data_Dictionary internal keys and cleaned second Key man List header."
    append_log(service, variables, details)
    print(json.dumps(variables, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
