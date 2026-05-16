from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.operation_log import LOG_HEADER, build_operation_row

load_dotenv(ROOT_DIR / ".env")


def required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


SERVICE_ACCOUNT_FILE = required_env("SERVICE_ACCOUNT_FILE")
SPREADSHEET_ID = required_env("SPREADSHEET_ID")
CRM_DESTINATION_SPREADSHEET_ID = os.getenv("CRM_DESTINATION_SPREADSHEET_ID", "").strip() or SPREADSHEET_ID
OLLAMA_URL = required_env("OLLAMA_URL")
OLLAMA_MODEL = required_env("OLLAMA_MODEL")
OLLAMA_TIMEOUT_SEC = int(os.getenv("CRM_OLLAMA_TIMEOUT_SEC", "30"))

LIST_SHEET = "List"
CRM_SHEET = "CRM"
LOG_SHEET_NAME = "log"
DICT_SHEET_NAME = "Data_Dictionary"

LIST_HEADER_ROW = 2
LIST_DATA_START_ROW = 3
CRM_HEADER_ROW = 1
CRM_WRITE_START_ROW = 3
DICT_SCAN_RANGE = f"{DICT_SHEET_NAME}!A:ZZ"
DICT_HEADER = ["sheet", "中文欄名", "internal_key", "type", "role", "note", "write_policy"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SOURCE_KEYS = [
    "top30",
    "region",
    "zone",
    "territory",
    "zip_code",
    "postal_code",
    "customer_name",
    "customer_aka",
    "customer_id",
    "customer_grade",
    "customer_grade_2025_h2",
    "priority_level",
    "phone_main",
    "clinic_phone",
    "customer_phone",
    "phone",
    "telephone",
    "tel",
    "external_sales_flag",
    "used_products",
    "recommended_product",
    "public_announcement",
    "has_public_announcement",
    "google_place_id",
    "placeid",
    "placedid",
    "business_hours_updated_at",
    "business_hours_updated",
    "internal_seminar",
    "external_symposium",
    "keyman_1_profile",
    "keyman_1_mobile",
    "keyman_1_birthday",
    "keyman_1_constellation",
    "keyman_1_talk_notes",
    "best_visit_time",
    "keyman_1_relationship",
    "keyman_2_profile",
    "keyman_2_mobile",
    "keyman_2_birthday",
    "keyman_2_constellation",
    "keyman_2_visit_time",
    "keyman_3_birthday",
    "keyman_3_constellation",
    "order_timing",
    "gce_code",
    "collection_mode",
    "billing_timing",
    "reconciliation_note",
    "collection_workflow_note",
    "special_attention",
    "relationship_temperature",
    "timely_topic",
    "primary_key_man",
    "key_man_1",
    "key_man_1_profile",
    "key_man_1_notice",
    "key_man_1_visit_time",
    "key_man_1_relationship",
    "key_man_2",
    "key_man_2_profile",
    "key_man_2_notice",
    "key_man_3",
    "key_man_3_profile",
    "other_notes",
    "order_notes",
    "payment_notes",
    "payment_status",
    "specialty",
    "last_visit_note",
    "customer_status_ai",
    "next_action",
    "action_reason",
    "doctor_personality",
    "proposed_line",
    "proposed_line_updated",
]

CRM_TARGET_MAP: dict[str, list[str]] = {
    "區域": ["region", "zone", "territory"],
    "郵區": ["zip_code", "postal_code"],
    "客戶簡稱": ["customer_name", "customer_aka"],
    "2025 H2 客戶等級": ["customer_grade_2025_h2", "customer_grade", "priority_level"],
    "診所/藥局電話": ["phone_main", "clinic_phone", "customer_phone", "phone", "telephone", "tel"],
    "既有產品": ["used_products", "recommended_product"],
    "有無對外銷售": [
        "external_sales_flag",
        "external_symposium",
        "business_hours_updated_at",
        "google_place_id",
        "business_hours_updated",
        "placeid",
        "placedid",
    ],
    "小型活動(診內) (時間、活動名稱 、相關產品)": ["internal_seminar"],
    "大型活動(診外) (時間、活動名稱、相關產品)": ["external_symposium"],
    "第一Key man(醫師)、電話(Line)、生日 (有多位聯絡人請分別填寫)": ["keyman_1_summary", "keyman_1_profile", "primary_key_man", "key_man_1", "key_man_1_profile"],
    "第一Key man(醫師)對談注意事項": ["keyman_1_talk_notes", "key_man_1_notice", "doctor_personality"],
    "第一Key man 拜訪時間": ["best_visit_time", "keyman_1_visit_time", "key_man_1_visit_time"],
    "第一Key man 九同關係": ["keyman_1_relationship", "key_man_1_relationship"],
    "第二Key man(藥師)、電話(Line)、生日、重要事項 (有多位聯絡人請分別填寫)": ["keyman_2_summary", "keyman_2_profile", "key_man_2", "key_man_2_profile"],
    "第三Key man(護理師)、電話(Line)、生日、重要事項 (有多位聯絡人請分別填寫)": ["keyman_3_summary", "key_man_3", "key_man_3_profile"],
    "其他事項": ["other_summary", "other_notes", "special_attention", "action_reason", "customer_status_ai"],
    "寄單事項 (寄單時間，聯絡人)": ["order_summary", "order_notes", "next_action"],
    "請款事項 (請款方式及時間，聯絡人)": ["payment_summary", "payment_notes", "payment_status"],
}

HEADER_ALIASES = {
    "對外": "external_sales_flag",
    "電話": "phone_main",
    "第一Key man(醫師)、電話(Line)、生日 (有多位聯絡人請分別填寫)": "keyman_1_profile",
    "行動電話1": "keyman_1_mobile",
    "生日": "keyman_1_birthday",
    "星座": "keyman_1_constellation",
    "第一Key man(醫師)對談注意事項": "keyman_1_talk_notes",
    "第一Key man 拜訪時間": "best_visit_time",
    "第一Key man 九同關係": "keyman_1_relationship",
    "第二Key man(藥師)、電話(Line)、生日、重要事項 (有多位聯絡人請分別填寫)": "keyman_2_profile",
    "行動電話2": "keyman_2_mobile",
    "第二Key man生日": "keyman_2_birthday",
    "第二Key man星座": "keyman_2_constellation",
    "拜訪時間": "keyman_2_visit_time",
    "第三Key man生日": "keyman_3_birthday",
    "第三Key man星座": "keyman_3_constellation",
    "寄單時間": "order_timing",
    "GCE": "gce_code",
    "寄單": "collection_mode",
    "請款時間": "billing_timing",
    "對帳": "reconciliation_note",
    "收款/對帳/匯款": "collection_workflow_note",
    "特別注意事項": "special_attention",
    "互動溫度": "relationship_temperature",
    "時事或笑話": "timely_topic",
    "placeId": "google_place_id",
    "營業時間更新日": "business_hours_updated_at",
}

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def safe_print(*values: Any) -> None:
    text = " ".join(str(value) for value in values)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding), flush=True)


def get_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    return build("sheets", "v4", credentials=creds)


def get_values(service, range_name: str, spreadsheet_id: str = SPREADSHEET_ID) -> list[list[str]]:
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
    ).execute()
    return result.get("values", [])


def update_values(
    service,
    range_name: str,
    values: list[list[str]],
    spreadsheet_id: str = SPREADSHEET_ID,
) -> None:
    body = {"values": values}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


def append_values(
    service,
    range_name: str,
    values: list[list[str]],
    spreadsheet_id: str = SPREADSHEET_ID,
) -> None:
    body = {"values": values}
    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def clear_values(service, range_name: str, spreadsheet_id: str = SPREADSHEET_ID) -> None:
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        body={},
    ).execute()


def get_sheet_id_by_name(
    service,
    sheet_name: str,
    spreadsheet_id: str = SPREADSHEET_ID,
) -> int | None:
    metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == sheet_name:
            return props.get("sheetId")
    return None


def ensure_sheet_exists(
    service,
    sheet_name: str,
    spreadsheet_id: str = SPREADSHEET_ID,
) -> None:
    if get_sheet_id_by_name(service, sheet_name, spreadsheet_id) is not None:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
    ).execute()


def normalize_header(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r", " ").replace("\n", " ")
    text = text.replace('"', "")
    text = re.sub(r"\s+", "", text)
    return text.strip().lower()


def safe_get(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx]).strip()


def truthy(value: Any) -> bool:
    text = str(value).strip().lower()
    return value is True or text in {"true", "1", "v", "y", "yes"}


def col_to_letter(col_num_1_based: int) -> str:
    result = ""
    while col_num_1_based > 0:
        col_num_1_based, remainder = divmod(col_num_1_based - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_header_index(headers: list[str]) -> dict[str, int]:
    return {normalize_header(header): i for i, header in enumerate(headers)}


def infer_write_policy(role: str, internal_key: str) -> str:
    role_key = normalize_header(role)
    internal = normalize_header(internal_key)
    if internal.startswith("ai") or internal in {"line_talk_script", "visit_strategy"}:
        return "ai"
    if role_key in {"action"}:
        return "script"
    if role_key in {"metric", "derived", "primarykey", "foreignkey", "primarytime"}:
        return "readonly"
    return "manual"


def find_dictionary_table(values: list[list[str]]) -> tuple[int, int, list[list[str]]]:
    expected = [normalize_header(header) for header in DICT_HEADER]
    for row_idx, row in enumerate(values):
        padded = row + [""] * (len(expected) - len(row))
        for col_idx in range(max(len(padded) - len(expected) + 1, 0)):
            candidate = [
                normalize_header(value)
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


def get_data_dictionary_values(service) -> tuple[list[list[str]], dict[str, int]]:
    values = get_values(service, DICT_SCAN_RANGE)
    if not values:
        raise RuntimeError(f"{DICT_SCAN_RANGE} is empty")
    header_row, start_col, sliced_values = find_dictionary_table(values)
    return sliced_values, {"header_row": header_row, "start_col": start_col}


def load_data_dictionary(service) -> dict[str, dict[str, str]]:
    values, _location = get_data_dictionary_values(service)
    if not values:
        raise RuntimeError("Data_Dictionary table is empty")

    result: dict[str, dict[str, str]] = {}
    for row in values[1:]:
        row = row + [""] * (7 - len(row))
        sheet_name = normalize_header(row[0])
        zh_header = str(row[1] or "").strip()
        internal_key = normalize_header(row[2])
        field_type = str(row[3] or "").strip()
        role = str(row[4] or "").strip()
        note = str(row[5] or "").strip()
        write_policy = str(row[6] or "").strip() or infer_write_policy(role, internal_key)

        if sheet_name != normalize_header(LIST_SHEET):
            continue
        if not internal_key or not zh_header:
            continue

        result[internal_key] = {
            "zh_header": zh_header,
            "type": field_type,
            "role": role,
            "note": note,
            "write_policy": write_policy,
        }

    return result


def build_index_map_from_dictionary(list_headers: list[str], dict_map: dict[str, dict[str, str]]) -> dict[str, int]:
    header_index = build_header_index(list_headers)
    index_map: dict[str, int] = {}

    for internal_key, meta in dict_map.items():
        normalized_zh = normalize_header(meta["zh_header"])
        if normalized_zh in header_index:
            index_map[internal_key] = header_index[normalized_zh]

    for header, internal_key in HEADER_ALIASES.items():
        normalized = normalize_header(header)
        if normalized in header_index and internal_key not in index_map:
            index_map[internal_key] = header_index[normalized]

    if "top30" not in index_map and normalize_header("Top30") in header_index:
        index_map["top30"] = header_index[normalize_header("Top30")]

    return index_map


def validate_required_keys(index_map: dict[str, int]) -> None:
    required = ["customer_name", "used_products", "last_visit_note", "top30"]
    missing = [key for key in required if key not in index_map]
    if missing:
        raise RuntimeError(f"Missing required internal keys or headers: {missing}")


def build_payload(row: list[str], index_map: dict[str, int]) -> dict[str, str]:
    payload = {key: safe_get(row, index_map.get(key)) for key in SOURCE_KEYS}
    payload["story_note"] = ""
    payload["keyman_1_summary"] = compose_keyman_summary(
        payload,
        [
            ("", "keyman_1_profile"),
            ("手機/Line", "keyman_1_mobile"),
            ("生日", "keyman_1_birthday"),
            ("星座", "keyman_1_constellation"),
        ],
    )
    payload["keyman_2_summary"] = compose_keyman_summary(
        payload,
        [
            ("", "keyman_2_profile"),
            ("手機/Line", "keyman_2_mobile"),
            ("生日", "keyman_2_birthday"),
            ("星座", "keyman_2_constellation"),
            ("拜訪時間", "keyman_2_visit_time"),
        ],
    )
    payload["keyman_3_summary"] = compose_keyman_summary(
        payload,
        [
            ("生日", "keyman_3_birthday"),
            ("星座", "keyman_3_constellation"),
        ],
    )
    payload["other_summary"] = compose_keyman_summary(
        payload,
        [
            ("特別注意", "special_attention"),
            ("互動溫度", "relationship_temperature"),
            ("狀態", "customer_status_ai"),
            ("行動原因", "action_reason"),
            ("GCE", "gce_code"),
        ],
    )
    payload["order_summary"] = compose_keyman_summary(
        payload,
        [
            ("寄單時間", "order_timing"),
            ("GCE", "gce_code"),
            ("寄單方式", "collection_mode"),
        ],
    )
    payload["payment_summary"] = compose_keyman_summary(
        payload,
        [
            ("請款時間", "billing_timing"),
            ("對帳", "reconciliation_note"),
            ("收款/對帳/匯款", "collection_workflow_note"),
            ("貨款狀態", "payment_status"),
            ("GCE", "gce_code"),
        ],
    )
    return payload


def compose_keyman_summary(payload: dict[str, str], fields: list[tuple[str, str]]) -> str:
    parts = []
    for label, key in fields:
        value = payload.get(key, "")
        if not value:
            continue
        value = compact_summary_value(value)
        parts.append(f"{label}: {value}" if label else value)
    return "\n".join(parts)[:700]


def compact_summary_value(value: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def build_story_prompt(payload: dict[str, str]) -> str:
    return (
        "Create a concise CRM follow-up note in Traditional Chinese. "
        "Use only the supplied customer facts. Keep it practical for a PSR.\n\n"
        f"客戶: {payload.get('customer_name', '')}\n"
        f"區域: {payload.get('region', '') or payload.get('zone', '')}\n"
        f"郵區: {payload.get('zip_code', '')}\n"
        f"既有產品: {payload.get('used_products', '')}\n"
        f"上次拜訪: {payload.get('last_visit_note', '')}\n"
        f"下一步: {payload.get('next_action', '')}\n"
        f"行動原因: {payload.get('action_reason', '')}\n"
        f"小型活動: {payload.get('internal_seminar', '')}\n"
        f"大型活動: {payload.get('external_symposium', '')}\n"
        f"其他事項: {payload.get('other_notes', '')}\n"
    )

def ask_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 220},
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT_SEC)
    response.raise_for_status()
    return response.json().get("response", "").strip()


def fallback_story_note(payload: dict[str, str]) -> str:
    parts = [
        payload.get("used_products", ""),
        payload.get("last_visit_note", ""),
        payload.get("next_action", ""),
        payload.get("internal_seminar", ""),
        payload.get("external_symposium", ""),
    ]
    parts = [part for part in parts if part]
    return " / ".join(parts)[:220]


def build_story_note(payload: dict[str, str], *, use_ollama: bool = True) -> str:
    if not use_ollama:
        return fallback_story_note(payload)

    prompt = build_story_prompt(payload)
    try:
        story = ask_ollama(prompt)
        return story[:300]
    except Exception as exc:
        safe_print(f"[WARN] Ollama story fallback for {payload.get('customer_name', '')}: {exc}")
        return fallback_story_note(payload)


def pick_payload_value(payload: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key, "")
        if value:
            return value
    return ""


def build_crm_row(
    list_row: list[str],
    list_index_map: dict[str, int],
    crm_headers: list[str],
    *,
    use_ollama: bool = True,
) -> list[str]:
    payload = build_payload(list_row, list_index_map)
    payload["story_note"] = build_story_note(payload, use_ollama=use_ollama)

    output = [""] * len(crm_headers)
    crm_index = build_header_index(crm_headers)

    for target_header, source_keys in CRM_TARGET_MAP.items():
        normalized_target = normalize_header(target_header)
        target_index = crm_index.get(normalized_target)
        if target_index is None:
            continue
        output[target_index] = pick_payload_value(payload, source_keys)

    return output


def ensure_log_header(service, spreadsheet_id: str = SPREADSHEET_ID) -> None:
    ensure_sheet_exists(service, LOG_SHEET_NAME, spreadsheet_id)
    existing = get_values(service, f"{LOG_SHEET_NAME}!A1:I2", spreadsheet_id)
    if existing and existing[0][: len(LOG_HEADER)] == LOG_HEADER:
        return

    update_values(
        service,
        f"{LOG_SHEET_NAME}!A1:I1",
        [LOG_HEADER],
        spreadsheet_id,
    )


def write_action_log(
    service,
    *,
    action: str,
    status: str,
    purpose: str,
    rows_processed: int,
    message: str,
    key_variables: str = "",
    maintenance_notes: str = "",
    spreadsheet_id: str = SPREADSHEET_ID,
) -> None:
    ensure_log_header(service, spreadsheet_id)
    variables = {}
    if key_variables:
        try:
            variables = json.loads(key_variables)
        except json.JSONDecodeError:
            variables = {"key_variables": key_variables}
    variables["rows_processed"] = rows_processed
    if maintenance_notes:
        variables["maintenance_notes"] = maintenance_notes

    append_values(
        service,
        f"{LOG_SHEET_NAME}!A:I",
        [
            build_operation_row(
                project_name=os.getenv("PROJECT_NAME", "psr-aios-v1"),
                operation=action,
                result=status.lower(),
                purpose=purpose,
                variables=variables,
                details=message,
            )
        ],
        spreadsheet_id,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh CRM from List via Data_Dictionary and current CRM headers."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build rows and print a summary without clearing or writing the CRM sheet.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Limit Top30 rows processed. 0 means all matching rows.",
    )
    parser.add_argument(
        "--skip-ollama",
        action="store_true",
        help="Use deterministic fallback story notes instead of calling Ollama.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = get_service()
    processed = 0

    try:
        safe_print("[STEP] Load Data_Dictionary")
        dict_map = load_data_dictionary(service)
        safe_print(f"[OK] Data_Dictionary keys: {len(dict_map)}")

        safe_print("[STEP] Load List and CRM headers")
        list_values = get_values(service, f"{LIST_SHEET}!A:ZZ")
        crm_values = get_values(
            service,
            f"{CRM_SHEET}!{CRM_HEADER_ROW}:{CRM_HEADER_ROW}",
            CRM_DESTINATION_SPREADSHEET_ID,
        )

        if len(list_values) < LIST_HEADER_ROW:
            raise RuntimeError("List sheet does not have the configured header row")
        if not crm_values:
            raise RuntimeError("CRM sheet does not have a header row")

        list_headers = list_values[LIST_HEADER_ROW - 1]
        list_rows = list_values[LIST_DATA_START_ROW - 1 :]
        crm_headers = crm_values[0]

        list_index_map = build_index_map_from_dictionary(list_headers, dict_map)
        validate_required_keys(list_index_map)
        safe_print(
            f"[OK] List rows={len(list_rows)} CRM columns={len(crm_headers)} "
            f"ollama={'off' if args.skip_ollama else 'on'} timeout={OLLAMA_TIMEOUT_SEC}s"
        )

        output_rows: list[list[str]] = []
        top30_rows = [
            (LIST_DATA_START_ROW + offset, row)
            for offset, row in enumerate(list_rows)
            if truthy(safe_get(row, list_index_map.get("top30")))
        ]
        if args.max_rows > 0:
            top30_rows = top30_rows[: args.max_rows]
        safe_print(f"[STEP] Build CRM rows from Top30 matches: {len(top30_rows)}")

        for index, (sheet_row, row) in enumerate(top30_rows, start=1):
            if not truthy(safe_get(row, list_index_map.get("top30"))):
                continue
            customer_name = safe_get(row, list_index_map.get("customer_name")) or "(no customer)"
            safe_print(f"[ROW] {index}/{len(top30_rows)} List row {sheet_row}: {customer_name}")
            output_rows.append(
                build_crm_row(
                    row,
                    list_index_map,
                    crm_headers,
                    use_ollama=not args.skip_ollama,
                )
            )
            processed += 1

        end_col = col_to_letter(len(crm_headers)) if crm_headers else "R"
        clear_range = f"{CRM_SHEET}!A{CRM_WRITE_START_ROW}:{end_col}"

        if args.dry_run:
            safe_print(
                f"[DRY-RUN] Built {processed} rows. Would clear {clear_range} "
                f"and write {len(output_rows)} rows."
            )
            if output_rows:
                safe_print("[DRY-RUN] First output row:")
                safe_print(json.dumps(output_rows[0], ensure_ascii=False)[:1200])
            return

        safe_print(f"[STEP] Clear CRM range {clear_range}")
        clear_values(service, clear_range, CRM_DESTINATION_SPREADSHEET_ID)

        write_range = ""
        if output_rows:
            write_range = f"{CRM_SHEET}!A{CRM_WRITE_START_ROW}:{end_col}{CRM_WRITE_START_ROW + len(output_rows) - 1}"
            safe_print(f"[STEP] Write CRM range {write_range}")
            update_values(
                service,
                write_range,
                output_rows,
                CRM_DESTINATION_SPREADSHEET_ID,
            )
        safe_print(f"[OK] Wrote {processed} CRM rows")

        write_action_log(
            service,
            action="crm_refresh",
            status="SUCCESS",
            purpose="Refresh CRM from List via Data_Dictionary and align to CRM target form",
            rows_processed=processed,
            message=(
                f"Wrote {processed} CRM rows to spreadsheet "
                f"{CRM_DESTINATION_SPREADSHEET_ID} range {write_range or clear_range}"
            ),
            key_variables=json.dumps(
                {
                    "model": OLLAMA_MODEL,
                    "source_spreadsheet_id": SPREADSHEET_ID,
                    "crm_destination_spreadsheet_id": CRM_DESTINATION_SPREADSHEET_ID,
                    "list_sheet": LIST_SHEET,
                    "crm_sheet": CRM_SHEET,
                    "crm_write_range": write_range,
                    "crm_clear_range": clear_range,
                    "new_keys": ["internal_seminar", "external_symposium"],
                    "target_columns": list(CRM_TARGET_MAP.keys()),
                },
                ensure_ascii=False,
            ),
            maintenance_notes="CRM source headers come from Data_Dictionary; CRM target columns are aligned to the current CRM form.",
            spreadsheet_id=CRM_DESTINATION_SPREADSHEET_ID,
        )
        safe_print("[DONE] CRM refresh complete")
    except Exception as exc:
        safe_print(f"[ERROR] CRM refresh failed: {exc}")
        try:
            write_action_log(
                service,
                action="crm_refresh",
                status="ERROR",
                purpose="Refresh CRM from List via Data_Dictionary and align to CRM target form",
                rows_processed=processed,
                message=str(exc),
                key_variables=json.dumps(
                    {
                        "model": OLLAMA_MODEL,
                        "source_spreadsheet_id": SPREADSHEET_ID,
                        "crm_destination_spreadsheet_id": CRM_DESTINATION_SPREADSHEET_ID,
                        "list_sheet": LIST_SHEET,
                        "crm_sheet": CRM_SHEET,
                        "new_keys": ["internal_seminar", "external_symposium"],
                    },
                    ensure_ascii=False,
                ),
                maintenance_notes="Check credentials, Data_Dictionary mappings, CRM header row, and Ollama availability.",
                spreadsheet_id=CRM_DESTINATION_SPREADSHEET_ID,
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
