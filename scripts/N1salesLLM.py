import json
import argparse
import re
import time
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# =========================
# 1) CONFIG
# =========================
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.operation_log import LOG_HEADER, build_operation_row

load_dotenv(ROOT_DIR / ".env")

def required_env(name):
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f'Missing required environment variable: {name}')

SERVICE_ACCOUNT_FILE = required_env('SERVICE_ACCOUNT_FILE')
SPREADSHEET_ID = required_env('SPREADSHEET_ID')
SHEET_NAME = "List"
LOG_SHEET_NAME = "log"
DICT_SHEET_NAME = "Data_Dictionary"

OLLAMA_URL = required_env('OLLAMA_URL')
OLLAMA_MODEL = required_env('OLLAMA_MODEL')

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

LIST_HEADER_ROW = 2
LIST_DATA_START_ROW = 3

# Data_Dictionary table is found by headers so the table block can move.
DICT_SCAN_RANGE = f"{DICT_SHEET_NAME}!A:ZZ"
DICT_HEADER = ["sheet", "中文欄名", "internal_key", "type", "role", "note", "write_policy"]

REQUIRED_KEYS = [
    "sales_1yr",
    "core6_1yr_sales",
    "last_visit_note",
    "used_products",
    "specialty",
    "customer_status_ai",
    "next_action",
]

OPTIONAL_KEYS = [
    "customer_name",
    "customer_id",
    "customer_aka",
    "doctor_personality",
    "priority_level",
    "action_reason",
    "payment_status",
]

WRITEBACK_KEYS = [
    "ai_action_proposal",
    "ai_recommended_product",
    "ai_product_reason",
    "ai_proposed_line",
    "ai_visit_angle",
]


# =========================
# 2) GOOGLE SHEETS API
# =========================
def get_sheets_service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def get_values(service, spreadsheet_id, range_name):
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name
    ).execute()
    return result.get("values", [])


def update_values(service, spreadsheet_id, range_name, values):
    body = {"values": values}
    return service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()


def append_values(service, spreadsheet_id, range_name, values):
    body = {"values": values}
    return service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()


def get_sheet_id_by_name(service, spreadsheet_id, sheet_name):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == sheet_name:
            return props.get("sheetId")
    return None


def ensure_sheet_exists(service, spreadsheet_id, sheet_name):
    if get_sheet_id_by_name(service, spreadsheet_id, sheet_name) is not None:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
    ).execute()


def ensure_log_header(service):
    ensure_sheet_exists(service, SPREADSHEET_ID, LOG_SHEET_NAME)
    existing = get_values(service, SPREADSHEET_ID, f"{LOG_SHEET_NAME}!A1:I2")
    if existing and existing[0][: len(LOG_HEADER)] == LOG_HEADER:
        return
    update_values(service, SPREADSHEET_ID, f"{LOG_SHEET_NAME}!A1:I1", [LOG_HEADER])


# =========================
# 3) HELPERS
# =========================
def normalize_header(v):
    return re.sub(r"\s+", " ", str(v or "").replace("\r", " ").replace("\n", " ")).strip()


def normalize_internal_key(v):
    return normalize_header(v).replace('"', "").lower()


def infer_write_policy(role, internal_key):
    role_key = normalize_internal_key(role)
    internal = normalize_internal_key(internal_key)
    if internal.startswith("ai_") or internal in {"line_talk_script", "visit_strategy"}:
        return "ai"
    if role_key == "action":
        return "script"
    if role_key in {"metric", "derived", "primary_key", "foreign_key", "primary_time"}:
        return "readonly"
    return "manual"


def find_dictionary_table(values):
    expected = [normalize_internal_key(header) for header in DICT_HEADER]
    for row_idx, row in enumerate(values):
        padded = row + [""] * (len(expected) - len(row))
        for col_idx in range(max(len(padded) - len(expected) + 1, 0)):
            candidate = [
                normalize_internal_key(value)
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
    raise ValueError(
        "Could not find Data_Dictionary table headers in "
        f"{DICT_SCAN_RANGE}: {', '.join(DICT_HEADER)}"
    )


def get_data_dictionary_values(service):
    values = get_values(service, SPREADSHEET_ID, DICT_SCAN_RANGE)
    if not values:
        raise ValueError(f"{DICT_SCAN_RANGE} is empty")
    header_row, start_col, sliced_values = find_dictionary_table(values)
    return sliced_values, {"header_row": header_row, "start_col": start_col}


def col_to_letter(col_num_1_based):
    result = ""
    while col_num_1_based > 0:
        col_num_1_based, remainder = divmod(col_num_1_based - 1, 26)
        result = chr(65 + remainder) + result
    return result


def safe_get(row, index_map, internal_key):
    idx = index_map.get(internal_key)
    if idx is None:
        return ""
    if idx >= len(row):
        return ""
    return str(row[idx]).strip()
def parse_json_from_text(text):
    raw = text.strip()

    # 1) ??????markdown code fence
    raw = re.sub(r"^```json\s*", "", raw, flags=re.I)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # 2) ??????parse
    try:
        obj = json.loads(raw)
        return ensure_ai_result_keys(obj)
    except Exception:
        pass

    # 3) ???單?豰刈???????
    match = re.search(r"\{.*\}", raw, re.S)
    if match:
        candidate = match.group(0)

        # 3a) ??????parse
        try:
            obj = json.loads(candidate)
            return ensure_ai_result_keys(obj)
        except Exception:
            pass

        # 3b) ?鞈?僱擗?????蹎抆????????
        repaired = candidate

        # ??Ⅹ??鞈??雓??鞈??頦?????
        repaired = re.sub(r"(?<!\\)'", '"', repaired)

        # ????雓?
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

        # ??謍啁?豰刈??
        try:
            obj = json.loads(repaired)
            return ensure_ai_result_keys(obj)
        except Exception:
            pass

    raise ValueError(f"Could not parse LLM response as JSON.\n{text}")


def ensure_ai_result_keys(obj):
    """
    ?謢??謅?雓? LLM ??銵????????????賃狀??豲??????????
    """
    required = [
        "ai_action_proposal",
        "ai_recommended_product",
        "ai_product_reason",
        "ai_proposed_line",
        "ai_visit_angle",
    ]

    if not isinstance(obj, dict):
        raise ValueError(f"LLM JSON result must be a dict: {type(obj)}")

    normalized = {}
    for k in required:
        normalized[k] = str(obj.get(k, "")).strip()

    return normalized

def write_action_log(service, action, status, purpose, rows_processed, message, key_variables="", maintenance_notes=""):
    ensure_log_header(service)
    variables = {}
    if key_variables:
        try:
            variables = json.loads(key_variables)
        except json.JSONDecodeError:
            variables = {"key_variables": key_variables}
    variables["rows_processed"] = rows_processed
    variables["sheet_name"] = SHEET_NAME
    if maintenance_notes:
        variables["maintenance_notes"] = maintenance_notes

    row = build_operation_row(
        project_name=os.getenv("PROJECT_NAME", "psr-aios-v1"),
        operation=action,
        result=str(status).lower(),
        purpose=purpose,
        variables=variables,
        details=message,
    )
    append_values(service, SPREADSHEET_ID, f"{LOG_SHEET_NAME}!A:I", [row])


# =========================
# 4) DATA DICTIONARY
# =========================
def load_data_dictionary(service):
    values, _location = get_data_dictionary_values(service)
    if not values:
        raise ValueError("Data_Dictionary table is empty")

    header = [normalize_internal_key(x) for x in values[0]]
    expected = [normalize_internal_key(x) for x in DICT_HEADER[:6]]
    if header[:6] != expected:
        raise ValueError(f"Data_Dictionary header mismatch: got {header[:6]}, expected {expected}")

    result = {}
    for row in values[1:]:
        row = row + [""] * (7 - len(row))
        sheet_name = normalize_header(row[0])
        zh_header = normalize_header(row[1])
        internal_key = normalize_internal_key(row[2])
        field_type = normalize_header(row[3])
        role = normalize_header(row[4])
        note = normalize_header(row[5])
        write_policy = normalize_header(row[6]) or infer_write_policy(role, internal_key)

        if sheet_name != SHEET_NAME:
            continue
        if not zh_header or not internal_key:
            continue

        result[internal_key] = {
            "zh_header": zh_header,
            "type": field_type,
            "role": role,
            "note": note,
            "write_policy": write_policy
        }

    return result


def build_index_map_from_dictionary(list_headers, dict_map):
    normalized_headers = [normalize_header(h) for h in list_headers]
    index_map = {}
    missing = []

    for internal_key, meta in dict_map.items():
        zh_header = normalize_header(meta["zh_header"])
        if zh_header in normalized_headers:
            index_map[internal_key] = normalized_headers.index(zh_header)
        else:
            missing.append(f"{internal_key} -> {zh_header}")

    if missing:
        print("WARNING: ?豯?????????List ??????")
        for m in missing:
            print(" -", m)

    return index_map


# =========================
# 5) READ LIST + BUILD PAYLOAD
# =========================
def load_list_sheet(service):
    header_values = get_values(service, SPREADSHEET_ID, f"{SHEET_NAME}!{LIST_HEADER_ROW}:{LIST_HEADER_ROW}")
    if not header_values:
        raise ValueError("List header row is empty")
    headers = header_values[0]

    data_values = get_values(service, SPREADSHEET_ID, f"{SHEET_NAME}!{LIST_DATA_START_ROW}:9999")
    return headers, data_values


def validate_required_keys(index_map):
    missing = [k for k in REQUIRED_KEYS if k not in index_map]
    if missing:
        raise ValueError(f"Missing required internal_key values: {missing}")


def validate_writeback_keys(index_map):
    missing = [key for key in WRITEBACK_KEYS if key not in index_map]
    if missing:
        raise ValueError(f"Missing writeback internal_key values: {missing}")


def build_payload(row, index_map):
    return {
        "customer_name": safe_get(row, index_map, "customer_name"),
        "customer_id": safe_get(row, index_map, "customer_id"),
        "customer_aka": safe_get(row, index_map, "customer_aka"),
        "doctor_personality": safe_get(row, index_map, "doctor_personality"),
        "specialty": safe_get(row, index_map, "specialty"),
        "used_products": safe_get(row, index_map, "used_products"),
        "sales_1yr": safe_get(row, index_map, "sales_1yr"),
        "core6_1yr_sales": safe_get(row, index_map, "core6_1yr_sales"),
        "last_visit_note": safe_get(row, index_map, "last_visit_note"),
        "customer_status_ai": safe_get(row, index_map, "customer_status_ai"),
        "next_action": safe_get(row, index_map, "next_action"),
        "priority_level": safe_get(row, index_map, "priority_level"),
        "action_reason": safe_get(row, index_map, "action_reason"),
        "payment_status": safe_get(row, index_map, "payment_status"),
    }


# =========================
# 6) OLLAMA PROMPT
# =========================
def build_fde_prompt(payload):
    return f"""
???雓Ⅹ?蹎???????岳??豯殷?????????FDE / Super Medical Sales Consultant?謅????

?????豯?????
???????謅????謅?ㄝ??????????亙??雓???豰刈頩????頦郁?頩?頩?謆?頩???豯頩?NE ??喉???頩???迎???????

????蝘???撗?
1. ??璈??謜眾??????JSON ???瑣??
2. ?豲???謜眾??markdown??
3. ?豲???謜眾??```json??
4. ?豲???謜眾??賃????頩????頩??嚚???
5. ???????捕??撠??????豲???
6. ????畾畸??豯???????謜眾??察?擳揚 JSON?謅?ㄜ????????????
7. JSON ?撠???????豯??? 5 ?????賃狀?
   - ai_action_proposal
   - ai_recommended_product
   - ai_product_reason
   - ai_proposed_line
   - ai_visit_angle

????????謜??
?嚚??????雓?
- sales_1yr
- core6_1yr_sales
- last_visit_note
- used_products
- specialty
- customer_status_ai
- next_action

??謅??豲???????????
- ??銵?紊???? -> ???
- ?豲??蝎察郁?????穿?謜?? -> ??賹竣
- ???????豲???????-> ???
- ??customer_status_ai = Collection -> ?????????雓??鞈???

????????謕???
- trust-first
- ?蹎???頩????謍頩??蝘????鞈?
- ?謍?????????謅?ㄜ??甇對??頩?
- ?頛舀????頩??豲??

?????????謢遴???謏???
{{
  "ai_action_proposal": "?璇???????鞊舀????????穿",
  "ai_recommended_product": "Major HA",
  "ai_product_reason": "??????????踝?? HA ??渡??????豲??????蝬??????????,
  "ai_proposed_line": "??蹎∵??鞊ｆ秣?謅?ㄞ??????賃郁?謜????蹎抒???格??????頛舀????????謖???????蝛??????雓?????????????謚????剜迫????謒?謅?ㄞ???????????頦揚?????蹎剁???????穿?????,
  "ai_visit_angle": "????????頛舀???船??????穿?謅?ㄝ???????????抵??????
}}

???遙????雓???
{json.dumps(payload, ensure_ascii=False, indent=2)}

???祉??嚚?????啣???JSON??
""".strip()


def build_fde_prompt(payload):
    return f"""
你是一位專業、細膩、可信任的醫療業務顧問，協助 PSR 針對單一客戶產生下一步行動建議。

請只根據提供的客戶資料判斷，不要捏造未提供的事實。若資料不足，請在內容中明確寫「需人工確認」。

輸出規則：
- 必須使用繁體中文。
- 必須只輸出一個 JSON object。
- 不要輸出 markdown、解釋、前言、後記或程式碼區塊。
- JSON 必須剛好包含以下 5 個 key：
  - ai_action_proposal
  - ai_recommended_product
  - ai_product_reason
  - ai_proposed_line
  - ai_visit_angle
- 每個 value 都必須是字串。
- ai_proposed_line 請控制在 120 字以內，適合直接貼給客戶 LINE。
- ai_visit_angle 請控制在 160 字以內，給業務拜訪時使用。
- 若 customer_status_ai 是 Collection 或與收款/請款相關，下一步要優先處理請款、對帳、付款時點或關係維護。

JSON 範例格式：
{{
  "ai_action_proposal": "先確認客戶目前需求與卡點，再安排低壓短訪。",
  "ai_recommended_product": "Major HA",
  "ai_product_reason": "既有資料顯示客戶曾接觸相關產品，可用回饋與使用情境延伸。",
  "ai_proposed_line": "您好，想跟您確認近期使用狀況與需求，若方便我這週找10分鐘跟您對一下。",
  "ai_visit_angle": "先確認最近使用/採購狀況，再釐清疑慮與下一步日期；避免強推，重點放在信任與具體後續。"
}}

客戶資料：
{json.dumps(payload, ensure_ascii=False, indent=2)}
""".strip()


def call_ollama(prompt):
    body = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": 420,
        },
    }

    resp = requests.post(OLLAMA_URL, json=body, timeout=120)
    resp.raise_for_status()

    data = resp.json()
    text = data.get("response", "").strip()

    if not text:
        raise ValueError("Ollama response is empty")

    return parse_json_from_text(text)

# =========================
# 7) WRITEBACK
# =========================
def writeback_ai_result(service, list_headers, index_map, row_num, ai_result):
    normalized_headers = [normalize_header(h) for h in list_headers]

    for internal_key in WRITEBACK_KEYS:
        if internal_key not in index_map:
            continue

        col_idx_0 = index_map[internal_key]
        col_letter = col_to_letter(col_idx_0 + 1)
        value = ai_result.get(internal_key, "")
        update_values(service, SPREADSHEET_ID, f"{SHEET_NAME}!{col_letter}{row_num}", [[value]])


# =========================
# 8) MAIN ENGINE
# =========================
def run_fde_ai_engine_v3_llm_ready(start_row=3, max_rows=5, writeback=False):
    service = get_sheets_service()
    t0 = time.time()
    processed = 0

    try:
        dict_map = load_data_dictionary(service)
        list_headers, list_rows = load_list_sheet(service)
        index_map = build_index_map_from_dictionary(list_headers, dict_map)
        validate_required_keys(index_map)
        if writeback:
            validate_writeback_keys(index_map)

        start_idx = max(start_row, LIST_DATA_START_ROW) - LIST_DATA_START_ROW
        rows_to_use = list_rows[start_idx:start_idx + max_rows]

        for offset, row in enumerate(rows_to_use):
            actual_row_num = start_row + offset

            payload = build_payload(row, index_map)
            if not payload.get("customer_name"):
                continue

            prompt = build_fde_prompt(payload)
            ai_result = call_ollama(prompt)

            print("=" * 80)
            print(f"ROW {actual_row_num} | {payload.get('customer_name')}")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print("-" * 40)
            print(json.dumps(ai_result, ensure_ascii=False, indent=2))

            if writeback:
                writeback_ai_result(service, list_headers, index_map, actual_row_num, ai_result)

            processed += 1

        elapsed = round(time.time() - t0, 2)
        write_action_log(
            service=service,
            action="run_fde_ai_engine_v3_llm_ready",
            status="SUCCESS",
            purpose="Run FDE AI engine over List payloads with Ollama.",
            rows_processed=processed,
            message=f"Processed {processed} rows in {elapsed}s",
            key_variables=json.dumps({
                "model": OLLAMA_MODEL,
                "writeback": writeback,
                "max_rows": max_rows,
                "start_row": start_row
            }, ensure_ascii=False),
            maintenance_notes="Uses configured Ollama model, log worksheet, and List sheet."
        )

    except Exception as e:
        write_action_log(
            service=service,
            action="run_fde_ai_engine_v3_llm_ready",
            status="ERROR",
            purpose="Run FDE AI engine over List payloads with Ollama.",
            rows_processed=processed,
            message=str(e),
            key_variables=json.dumps({
                "model": OLLAMA_MODEL,
                "writeback": writeback,
                "max_rows": max_rows,
                "start_row": start_row
            }, ensure_ascii=False),
            maintenance_notes="Check credentials, Data_Dictionary, and Ollama."
        )
        raise
# =========================
# 9) DEBUG
# =========================

def debug_single_row_llm(start_row=3):
    service = get_sheets_service()

    dict_map = load_data_dictionary(service)
    list_headers, list_rows = load_list_sheet(service)
    index_map = build_index_map_from_dictionary(list_headers, dict_map)
    validate_required_keys(index_map)

    idx = start_row - LIST_DATA_START_ROW
    if idx < 0 or idx >= len(list_rows):
        raise ValueError(f"Row {start_row} ?豯殷???List ???????")

    row = list_rows[idx]
    payload = build_payload(row, index_map)

    prompt = build_fde_prompt(payload)

    print("=" * 80)
    print("PAYLOAD")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("=" * 80)
    print("PROMPT")
    print(prompt)
    print("=" * 80)

    result = call_ollama(prompt)

    print("PARSED RESULT")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("=" * 80)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run N1 FDE AI recommendations over List rows."
    )
    parser.add_argument("--start-row", type=int, default=23)
    parser.add_argument("--max-rows", type=int, default=5)
    parser.add_argument(
        "--writeback",
        action="store_true",
        help="Write AI results back to List. Omit for a safe preview run.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print one row payload/prompt/result instead of batch processing.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.debug:
        debug_single_row_llm(start_row=args.start_row)
    else:
        run_fde_ai_engine_v3_llm_ready(
            start_row=args.start_row,
            max_rows=args.max_rows,
            writeback=args.writeback
        )
