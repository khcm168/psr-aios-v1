import argparse
import json
import re
import time
from datetime import datetime
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

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


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate LINE話術 and 拜訪策略 for List rows."
    )
    parser.add_argument("--start-row", type=int, default=START_ROW)
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Limit rows for chunked runs. 0 means process through the last row.",
    )
    return parser.parse_args()


def safe_print(*values, **kwargs):
    text = " ".join(str(value) for value in values)
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_text = text.encode(encoding, errors="replace").decode(encoding)
        print(safe_text, **kwargs)

SERVICE_ACCOUNT_FILE = required_env('SERVICE_ACCOUNT_FILE')
SPREADSHEET_ID = required_env('SPREADSHEET_ID')
SHEET_NAME = "List"
LOG_SHEET_NAME = "log"

OLLAMA_URL = required_env('OLLAMA_URL')
OLLAMA_MODEL = required_env('OLLAMA_MODEL')

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

START_ROW = 3
BATCH_SIZE = 15

# Source headers used by the visit-plan generator
SOURCE_HEADERS = {
    "region": "區域",
    "customer_name": "客戶名稱",
    "visit_history": "上次拜訪",
    "sales_hist_1": "既有產品銷售歷史",
    "sales_hist_2": "六大品項一年內銷售",
}

# Output headers written by the visit-plan generator
OUTPUT_HEADERS = {
    "line_text": "LINE話術",
    "visit_text": "拜訪策略",
}

PROMPT_TEMPLATE_PATH = Path(
    os.getenv("VISITINGPLAN_PROMPT_TEMPLATE", ROOT_DIR / "docs" / "prompts" / "visitingplan.md")
)

DEFAULT_PROMPT_TEMPLATE = """
你是一位專業、細膩、可信任的醫療業務顧問。
請根據客戶的拜訪紀錄與銷售歷史，產出兩段內容：
1. LINE 話術：輕鬆自然、低壓、信任導向。
2. 拜訪策略：具體下一步行動，可直接給業務執行。

規則：
- 使用繁體中文。
- 不要捏造未提供的事實。
- 若資料不足，明確提醒需要人工確認。
- LINE 保持 120 字以內。
- PLAN 保持 380 字以內。
- 回覆格式必須只有：
LINE:
...
PLAN:
...

[客戶資訊]
區域：{region}
客戶名稱：{customer_name}

[銷售歷史]
{history_sales}

[拜訪紀錄]
{visit_notes}
""".strip()


# =========================
# 2) GOOGLE SHEETS CLIENT
# =========================
def get_sheets_service():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds)


def batch_get_values(service, spreadsheet_id, ranges):
    result = service.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=ranges
    ).execute()
    return result.get("valueRanges", [])


def update_values(service, spreadsheet_id, write_range, values):
    body = {"values": values}
    return service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=write_range,
        valueInputOption="RAW",
        body=body
    ).execute()


def append_values(service, spreadsheet_id, append_range, values):
    body = {"values": values}
    return service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=append_range,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()


def get_sheet_id_by_name(service, spreadsheet_id, sheet_name):
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta.get("sheets", []):
        props = s.get("properties", {})
        if props.get("title") == sheet_name:
            return props.get("sheetId")
    return None


def ensure_sheet_exists(service, spreadsheet_id, sheet_name):
    sheet_id = get_sheet_id_by_name(service, spreadsheet_id, sheet_name)
    if sheet_id is not None:
        return sheet_id

    body = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": sheet_name
                    }
                }
            }
        ]
    }
    result = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body
    ).execute()
    replies = result.get("replies", [])
    if replies:
        return replies[0]["addSheet"]["properties"]["sheetId"]
    return get_sheet_id_by_name(service, spreadsheet_id, sheet_name)


def ensure_log_header(service, spreadsheet_id):
    ensure_sheet_exists(service, spreadsheet_id, LOG_SHEET_NAME)
    header_range = f"{LOG_SHEET_NAME}!A1:I2"
    existing = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=header_range
    ).execute().get("values", [])

    if existing and existing[0][: len(LOG_HEADER)] == LOG_HEADER:
        return

    update_values(service, spreadsheet_id, f"{LOG_SHEET_NAME}!A1:I1", [LOG_HEADER])


def append_log_row(service, spreadsheet_id, row_values):
    append_values(service, spreadsheet_id, f"{LOG_SHEET_NAME}!A:I", [row_values])


def append_operation_log(
    service,
    spreadsheet_id,
    *,
    result,
    purpose,
    variables,
    details,
):
    ensure_log_header(service, spreadsheet_id)
    append_log_row(
        service,
        spreadsheet_id,
        build_operation_row(
            project_name=os.getenv("PROJECT_NAME", "psr-aios-v1"),
            operation="visitingplan.py",
            result=result,
            purpose=purpose,
            variables=variables,
            details=details,
        ),
    )


# =========================
# 3) SHEET RANGE DETECTION
# =========================
def get_last_nonempty_row(service, spreadsheet_id, sheet_name, col="C"):
    """Return the last non-empty row in the selected column."""
    rng = f"{sheet_name}!{col}:{col}"
    values = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=rng
    ).execute().get("values", [])

    last_row = 0
    for idx, row in enumerate(values, start=1):
        cell = row[0].strip() if row and row[0] else ""
        if cell:
            last_row = idx
    return last_row


def build_read_ranges(sheet_name, start_row, end_row, source_cols):
    return [
        f"{sheet_name}!{source_cols['region']}{start_row}:{source_cols['region']}{end_row}",
        f"{sheet_name}!{source_cols['customer_name']}{start_row}:{source_cols['customer_name']}{end_row}",
        f"{sheet_name}!{source_cols['visit_history']}{start_row}:{source_cols['visit_history']}{end_row}",
        f"{sheet_name}!{source_cols['sales_hist_1']}{start_row}:{source_cols['sales_hist_1']}{end_row}",
        f"{sheet_name}!{source_cols['sales_hist_2']}{start_row}:{source_cols['sales_hist_2']}{end_row}",
    ]


# =========================
# 4) DATA CLEANING
# =========================
def normalize_text(x):
    if x is None:
        return ""
    if isinstance(x, list):
        x = " ".join(str(v) for v in x)
    x = str(x).replace("\r", "\n")
    x = "\n".join(line.strip() for line in x.split("\n"))
    while "\n\n\n" in x:
        x = x.replace("\n\n\n", "\n\n")
    return x.strip()


def safe_get_2d(values, row_idx, col_idx):
    try:
        return values[row_idx][col_idx]
    except Exception:
        return ""


def compact_text(text, max_len=600):
    text = normalize_text(text)
    text = re.sub(r"[ \t]+", " ", text)
    return text[:max_len] if len(text) > max_len else text


def normalize_header(value):
    return re.sub(r"\s+", "", str(value or "").replace("\r", " ").replace("\n", " ")).strip().lower()


def col_to_letter(col_num_1_based):
    result = ""
    while col_num_1_based > 0:
        col_num_1_based, remainder = divmod(col_num_1_based - 1, 26)
        result = chr(65 + remainder) + result
    return result


def letter_to_col(col_letters):
    result = 0
    for char in col_letters:
        result = result * 26 + (ord(char.upper()) - ord("A") + 1)
    return result


def header_index_map(headers):
    return {normalize_header(header): idx for idx, header in enumerate(headers)}


def require_header_col(headers, header_name):
    index = header_index_map(headers).get(normalize_header(header_name))
    if index is None:
        raise RuntimeError(f"Missing required List header: {header_name}")
    return col_to_letter(index + 1)


def read_prompt_template():
    if PROMPT_TEMPLATE_PATH.exists():
        return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    return DEFAULT_PROMPT_TEMPLATE


# =========================
# 5) PROMPT DESIGN
# =========================
def build_combined_prompt(region, customer_name, visit_history, sales_hist_1, sales_hist_2):
    visit_history = compact_text(visit_history, 900)
    sales_hist_1 = compact_text(sales_hist_1, 600)
    sales_hist_2 = compact_text(sales_hist_2, 600)
    history_sales = "\n".join(
        item for item in [sales_hist_1, sales_hist_2] if item
    ) or "No sales history provided."
    visit_notes = visit_history or "No visit history provided."

    return read_prompt_template().format(
        region=region or "未提供",
        customer_name=customer_name or "未提供",
        history_sales=history_sales,
        visit_notes=visit_notes,
    )


# =========================
# 6) OLLAMA
# =========================
def ask_ollama(prompt, model=OLLAMA_MODEL, timeout=180):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.35,
            "top_p": 0.9,
            "num_predict": 420
        }
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data.get("response", "").strip()


def parse_combined_output(text, customer_name=""):
    text = normalize_text(text)

    line_text = ""
    visit_text = ""

    line_match = re.search(
        r"LINE\s*[:=]\s*(.*?)(?:\n\s*(?:PLAN|VISIT)\s*[:=]|\Z)",
        text,
        flags=re.S | re.I,
    )
    visit_match = re.search(r"(?:PLAN|VISIT)\s*[:=]\s*(.*)$", text, flags=re.S | re.I)

    if line_match:
        line_text = normalize_text(line_match.group(1))
    if visit_match:
        visit_text = normalize_text(visit_match.group(1))

    if not line_text:
        name = customer_name or "doctor"
        line_text = f"{name}, I prepared a short follow-up note and visit plan for our next contact."

    if not visit_text:
        visit_text = (
            "目前資料不足或模型未依格式輸出，請先人工確認最近拜訪紀錄與銷售變化。\n"
            "下一步：用低壓方式確認需求，再記錄客戶回應。"
        )

    line_text = re.sub(r"^LINE[：:\s-]*", "", line_text, flags=re.I)
    visit_text = re.sub(r"^(PLAN|VISIT)[：:\s-]*", "", visit_text, flags=re.I)

    line_text = compact_text(line_text, 140)
    visit_text = compact_text(visit_text, 380)
    return line_text, visit_text

def generate_be_bf(region, customer_name, visit_history, sales_hist_1, sales_hist_2):
    prompt = build_combined_prompt(
        region=region,
        customer_name=customer_name,
        visit_history=visit_history,
        sales_hist_1=sales_hist_1,
        sales_hist_2=sales_hist_2
    )
    prompt_chars = len(prompt)

    t0 = time.time()
    raw = ask_ollama(prompt)
    elapsed = time.time() - t0
    output_chars = len(raw)

    line_text, visit_text = parse_combined_output(raw, customer_name)
    return line_text, visit_text, prompt_chars, output_chars, elapsed


# =========================
# 7) BATCH WRITE
# =========================
def flush_batch(
    service,
    spreadsheet_id,
    sheet_name,
    start_row,
    rows_2d,
    *,
    write_start_col,
    write_end_col,
):
    if not rows_2d:
        return None
    end_row = start_row + len(rows_2d) - 1
    write_range = f"{sheet_name}!{write_start_col}{start_row}:{write_end_col}{end_row}"
    result = update_values(service, spreadsheet_id, write_range, rows_2d)
    safe_print(f"Updated range: {result.get('updatedRange')}")
    return result


# =========================
# 8) MAIN
# =========================
def main():
    args = parse_args()
    start_row = args.start_row
    script_start = time.time()
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    service = get_sheets_service()
    ensure_log_header(service, SPREADSHEET_ID)

    headers = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!2:2",
    ).execute().get("values", [[]])[0]
    source_cols = {
        key: require_header_col(headers, header)
        for key, header in SOURCE_HEADERS.items()
    }
    output_cols = {
        key: require_header_col(headers, header)
        for key, header in OUTPUT_HEADERS.items()
    }
    write_start_col = output_cols["line_text"]
    write_end_col = output_cols["visit_text"]
    if letter_to_col(write_end_col) != letter_to_col(write_start_col) + 1:
        raise RuntimeError(
            "Visiting plan output headers must be adjacent: "
            f"{OUTPUT_HEADERS['line_text']}={write_start_col}, "
            f"{OUTPUT_HEADERS['visit_text']}={write_end_col}"
        )

    end_row = get_last_nonempty_row(
        service,
        SPREADSHEET_ID,
        SHEET_NAME,
        col=source_cols["customer_name"],
    )
    if args.max_rows > 0:
        end_row = min(end_row, start_row + args.max_rows - 1)

    if end_row < start_row:
        note = f"No data found in {SHEET_NAME}!C:C from row {start_row}"
        append_operation_log(
            service,
            SPREADSHEET_ID,
            result="skipped",
            purpose="Generate visit-plan BE/BF text from List sheet source columns.",
            variables={
                "sheet_name": SHEET_NAME,
                "start_row": start_row,
                "end_row": end_row,
                "processed_rows": 0,
                "elapsed_sec": round(time.time() - script_start, 2),
            },
            details=note,
        )
        safe_print(note)
        return

    read_ranges = build_read_ranges(SHEET_NAME, start_row, end_row, source_cols)
    value_ranges = batch_get_values(service, SPREADSHEET_ID, read_ranges)

    region_vals = value_ranges[0].get("values", [])
    customer_vals = value_ranges[1].get("values", [])
    visit_vals = value_ranges[2].get("values", [])
    sales_1_vals = value_ranges[3].get("values", [])
    sales_2_vals = value_ranges[4].get("values", [])

    total_rows = end_row - start_row + 1
    batch_rows = []
    batch_start_sheet_row = None

    success_rows = 0
    error_rows = 0
    skipped_rows = 0
    total_prompt_chars = 0
    total_output_chars = 0
    total_llm_sec = 0.0
    error_samples = []

    for i in range(total_rows):
        sheet_row = start_row + i

        region = normalize_text(safe_get_2d(region_vals, i, 0))
        customer_name = normalize_text(safe_get_2d(customer_vals, i, 0))
        visit_history = normalize_text(safe_get_2d(visit_vals, i, 0))
        sales_hist_1 = normalize_text(safe_get_2d(sales_1_vals, i, 0))
        sales_hist_2 = normalize_text(safe_get_2d(sales_2_vals, i, 0))

        if not customer_name and not visit_history and not sales_hist_1 and not sales_hist_2:
            line_text = ""
            visit_text = ""
            skipped_rows += 1
            prompt_chars = 0
            output_chars = 0
            llm_sec = 0.0
            safe_print(f"[SKIP] Row {sheet_row} empty")
        else:
            try:
                line_text, visit_text, prompt_chars, output_chars, llm_sec = generate_be_bf(
                    region=region,
                    customer_name=customer_name,
                    visit_history=visit_history,
                    sales_hist_1=sales_hist_1,
                    sales_hist_2=sales_hist_2
                )
                success_rows += 1
                safe_print(
                    f"[OK] Row {sheet_row} {customer_name} | "
                    f"prompt_chars={prompt_chars} | output_chars={output_chars} | "
                    f"llm_sec={llm_sec:.2f}"
                )
            except Exception as e:
                error_rows += 1
                err_msg = str(e)[:120]
                if len(error_samples) < 5:
                    error_samples.append(f"row{sheet_row}:{err_msg}")

                line_text = (
                    f"{customer_name or '客戶'}您好，想跟您確認近期使用狀況，若方便我再安排一次簡短拜訪。"
                )
                visit_text = (
                    "LLM 產生失敗，請人工確認此列拜訪紀錄與銷售歷史。\n"
                    f"下一步：檢查 Ollama/service error: {err_msg}"
                )
                prompt_chars = 0
                output_chars = 0
                llm_sec = 0.0
                safe_print(f"[ERROR] Row {sheet_row} {customer_name}: {err_msg}")

        total_prompt_chars += prompt_chars
        total_output_chars += output_chars
        total_llm_sec += llm_sec

        if batch_start_sheet_row is None:
            batch_start_sheet_row = sheet_row

        batch_rows.append([line_text, visit_text])

        if len(batch_rows) >= BATCH_SIZE:
            flush_batch(
                service=service,
                spreadsheet_id=SPREADSHEET_ID,
                sheet_name=SHEET_NAME,
                start_row=batch_start_sheet_row,
                rows_2d=batch_rows,
                write_start_col=write_start_col,
                write_end_col=write_end_col,
            )
            batch_rows = []
            batch_start_sheet_row = None

        time.sleep(0.10)

    if batch_rows:
        flush_batch(
            service=service,
            spreadsheet_id=SPREADSHEET_ID,
            sheet_name=SHEET_NAME,
            start_row=batch_start_sheet_row,
            rows_2d=batch_rows,
            write_start_col=write_start_col,
            write_end_col=write_end_col,
        )

    elapsed_total = round(time.time() - script_start, 2)
    processed_rows = total_rows - skipped_rows
    avg_prompt = round(total_prompt_chars / processed_rows, 1) if processed_rows else 0
    avg_output = round(total_output_chars / processed_rows, 1) if processed_rows else 0
    avg_llm_sec = round(total_llm_sec / processed_rows, 2) if processed_rows else 0

    note = (
        f"model={OLLAMA_MODEL}; batch={BATCH_SIZE}; "
        f"avg_prompt_chars={avg_prompt}; avg_output_chars={avg_output}; "
        f"avg_llm_sec={avg_llm_sec}"
    )
    if error_samples:
        note += " | errors=" + " ; ".join(error_samples)

    append_operation_log(
        service,
        SPREADSHEET_ID,
        result="success" if error_rows == 0 else "partial",
        purpose="Generate visit-plan BE/BF text from List sheet source columns.",
        variables={
            "sheet_name": SHEET_NAME,
            "start_row": start_row,
            "end_row": end_row,
            "max_rows": args.max_rows,
            "processed_rows": processed_rows,
            "success_rows": success_rows,
            "error_rows": error_rows,
            "skipped_rows": skipped_rows,
            "elapsed_sec": elapsed_total,
            "model": OLLAMA_MODEL,
            "batch_size": BATCH_SIZE,
            "source_headers": SOURCE_HEADERS,
            "source_cols": source_cols,
            "output_headers": OUTPUT_HEADERS,
            "output_cols": output_cols,
        },
        details=note,
    )

    safe_print(
        f"Done. Updated {SHEET_NAME}!{write_start_col}{start_row}:{write_end_col}{end_row} | "
        f"processed={processed_rows} success={success_rows} error={error_rows} "
        f"skipped={skipped_rows} elapsed={elapsed_total}s"
    )


def safe_main():
    try:
        main()
    except Exception as exc:
        try:
            service = get_sheets_service()
            append_operation_log(
                service,
                SPREADSHEET_ID,
                result="failure",
                purpose="Generate visit-plan BE/BF text from List sheet source columns.",
                variables={
                    "sheet_name": SHEET_NAME,
                    "start_row": START_ROW,
                    "output_headers": OUTPUT_HEADERS,
                    "model": OLLAMA_MODEL,
                },
                details=str(exc)[:500],
            )
        except Exception as log_exc:
            safe_print(f"WARNING: failed to append visitingplan failure log: {log_exc}")
        raise


if __name__ == "__main__":
    safe_main()
