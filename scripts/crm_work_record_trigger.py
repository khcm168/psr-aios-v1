from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRIGGER_VALUE = "work record keyin"
RESET_VALUE = "none"
DEFAULT_COMPANY = "TOP高峰藥品"
DEFAULT_SHEET_TAB = "V"
DEFAULT_TRIGGER_CELL = "T1"
OUTPUT_DIR = ROOT / "data" / "crm_work_record_trigger"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


@dataclass(frozen=True)
class TriggerConfig:
    sheet_tab: str
    trigger_cell: str
    trigger_value: str
    reset_value: str
    poll_seconds: int
    once: bool
    dry_run: bool
    company: str
    date: str
    max_rows: int
    keep_open: bool


@dataclass(frozen=True)
class SheetContext:
    service: Any
    spreadsheet_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Watch a Google Sheets dropdown cell and run crm_work_record_lookup.py "
            "when it is set to the trigger value."
        )
    )
    parser.add_argument("--sheet-tab", default=DEFAULT_SHEET_TAB, help="Trigger sheet tab. Default: V.")
    parser.add_argument("--trigger-cell", default=DEFAULT_TRIGGER_CELL, help="Trigger cell. Default: T1.")
    parser.add_argument(
        "--trigger-value",
        default=TRIGGER_VALUE,
        help="Dropdown value that starts CRM key-in. Default: work record keyin.",
    )
    parser.add_argument("--reset-value", default=RESET_VALUE, help="Value to write after a run. Default: none.")
    parser.add_argument("--poll-seconds", type=int, default=15, help="Watch interval. Default: 15.")
    parser.add_argument("--once", action="store_true", help="Check once, then exit.")
    parser.add_argument("--dry-run", action="store_true", help="Print/log the intended command without running CRM.")
    parser.add_argument("--company", default=DEFAULT_COMPANY, help="CRM company visible text.")
    parser.add_argument("--date", default="", help="Optional CRM sheet date override, e.g. 2026/5/29.")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional CRM max rows. 0 means all matching rows.")
    parser.add_argument("--keep-open", action="store_true", help="Pass --keep-open to the CRM browser run.")
    return parser.parse_args()


def load_dotenv_files() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    for dotenv_path in (Path.cwd() / ".env", ROOT / ".env"):
        load_dotenv(dotenv_path)


def build_config(args: argparse.Namespace) -> TriggerConfig:
    return TriggerConfig(
        sheet_tab=args.sheet_tab,
        trigger_cell=args.trigger_cell,
        trigger_value=args.trigger_value,
        reset_value=args.reset_value,
        poll_seconds=max(1, args.poll_seconds),
        once=args.once,
        dry_run=args.dry_run,
        company=args.company,
        date=args.date,
        max_rows=max(0, args.max_rows),
        keep_open=args.keep_open,
    )


def required_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def open_sheet_context() -> SheetContext:
    load_dotenv_files()
    try:
        import _cffi_backend  # noqa: F401
    except Exception:
        pass
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_service_account_file(
        required_env("GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_FILE"),
        scopes=SHEETS_SCOPES,
    )
    service = build("sheets", "v4", credentials=credentials)
    return SheetContext(
        service=service,
        spreadsheet_id=required_env("GOOGLE_SHEET_ID", "N1_SOURCE_SPREADSHEET_ID", "SPREADSHEET_ID"),
    )


def sheet_range(sheet_name: str, a1_range: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'!{a1_range}"


def get_values(context: SheetContext, range_name: str) -> list[list[str]]:
    result = execute_with_retry(
        lambda: context.service.spreadsheets().values().get(
            spreadsheetId=context.spreadsheet_id,
            range=range_name,
            valueRenderOption="FORMATTED_VALUE",
        ),
        f"read {range_name}",
    )
    return result.get("values", [])


def update_values(context: SheetContext, range_name: str, values: list[list[str]]) -> None:
    execute_with_retry(
        lambda: context.service.spreadsheets().values().update(
            spreadsheetId=context.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ),
        f"update {range_name}",
    )


def append_values(context: SheetContext, range_name: str, values: list[list[str]]) -> None:
    execute_with_retry(
        lambda: context.service.spreadsheets().values().append(
            spreadsheetId=context.spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ),
        f"append {range_name}",
    )


def execute_with_retry(build_request: Any, label: str, attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return build_request().execute(num_retries=2)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            print(f"[WARN] Google Sheets {label} failed on attempt {attempt}: {exc}", flush=True)
            time.sleep(min(15, attempt * 5))
    raise RuntimeError(f"Google Sheets {label} failed after {attempts} attempts: {last_error}") from last_error


def read_trigger_value(context: SheetContext, config: TriggerConfig) -> str:
    values = get_values(context, sheet_range(config.sheet_tab, config.trigger_cell))
    return str(values[0][0] if values and values[0] else "").strip()


def reset_trigger_value(context: SheetContext, config: TriggerConfig) -> None:
    update_values(context, sheet_range(config.sheet_tab, config.trigger_cell), [[config.reset_value]])


def values_match(actual: str, expected: str) -> bool:
    return actual.strip().casefold() == expected.strip().casefold()


def build_crm_command(config: TriggerConfig) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "crm_work_record_lookup.py"),
        "--company",
        config.company,
    ]
    if config.date:
        command.extend(["--date", config.date])
    if config.max_rows:
        command.extend(["--max-rows", str(config.max_rows)])
    if config.keep_open:
        command.append("--keep-open")
    return command


def append_log(
    context: SheetContext,
    config: TriggerConfig,
    *,
    operation: str,
    result: str,
    purpose: str,
    variables: dict[str, Any],
    details: str = "",
) -> None:
    from app.operation_log import LOG_HEADER, build_operation_row

    header_range = sheet_range("log", "A1:I1")
    existing_header = get_values(context, header_range)
    if not existing_header or existing_header[0][: len(LOG_HEADER)] != LOG_HEADER:
        update_values(context, header_range, [LOG_HEADER])
    row = build_operation_row(
        project_name=os.getenv("PROJECT_NAME", "psr-aios-v1"),
        operation=operation,
        result=result,
        purpose=purpose,
        variables=variables,
        details=details,
    )
    append_values(context, sheet_range("log", "A:I"), [row])


def output_log_path() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"crm_work_record_lookup_{stamp}.log"


def run_crm(config: TriggerConfig) -> tuple[int, Path, str]:
    command = build_crm_command(config)
    log_path = output_log_path()
    command_text = subprocess.list2cmdline(command)
    if config.dry_run:
        output = f"[DRY-RUN] {command_text}\n"
        log_path.write_text(output, encoding="utf-8")
        print(output, end="")
        return 0, log_path, output

    print(f"[STEP] Running CRM command: {command_text}", flush=True)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    log_path.write_text(output, encoding="utf-8")
    print(output, end="", flush=True)
    return completed.returncode, log_path, output


def output_summary(output: str) -> dict[str, Any]:
    loaded_match = re.search(r"Loaded\s+(\d+)\s+sheet row", output)
    saved_rows = re.findall(r"Save record:\s+sheet row\s+(\d+)", output)
    return {
        "loaded_rows": int(loaded_match.group(1)) if loaded_match else None,
        "saved_sheet_rows": saved_rows,
    }


def handle_trigger(context: SheetContext, config: TriggerConfig, trigger_value: str) -> None:
    command = build_crm_command(config)
    base_variables = {
        "sheet_tab": config.sheet_tab,
        "trigger_cell": config.trigger_cell,
        "trigger_value": trigger_value,
        "reset_value": config.reset_value,
        "command": subprocess.list2cmdline(command),
        "dry_run": config.dry_run,
    }
    append_log(
        context,
        config,
        operation="crm-work-record-keyin-trigger",
        result="started",
        purpose="Sheet V dropdown triggered CRM work record key-in.",
        variables=base_variables,
    )

    return_code = 1
    log_path = Path()
    output = ""
    reset_result = "not attempted"
    try:
        return_code, log_path, output = run_crm(config)
    finally:
        try:
            reset_trigger_value(context, config)
            reset_result = "reset"
            print(f"[OK] Reset {config.sheet_tab}!{config.trigger_cell} to {config.reset_value}", flush=True)
        except Exception as exc:
            reset_result = f"reset failed: {exc}"
            print(f"[WARN] {reset_result}", flush=True)

    result = "success" if return_code == 0 else "error"
    variables = {
        **base_variables,
        "return_code": return_code,
        "output_log": str(log_path) if log_path else "",
        "trigger_reset": reset_result,
        **output_summary(output),
    }
    append_log(
        context,
        config,
        operation="crm-work-record-keyin-trigger",
        result=result,
        purpose="CRM work record key-in completed from Sheet V dropdown.",
        variables=variables,
        details=str(log_path) if log_path else "",
    )
    if return_code != 0:
        raise RuntimeError(f"CRM command failed with exit code {return_code}. See {log_path}")


def run(config: TriggerConfig) -> None:
    context = open_sheet_context()
    print(
        f"[WATCH] {config.sheet_tab}!{config.trigger_cell} == {config.trigger_value!r} "
        f"will run CRM key-in; reset value is {config.reset_value!r}.",
        flush=True,
    )
    while True:
        trigger_value = read_trigger_value(context, config)
        print(f"[CHECK] {config.sheet_tab}!{config.trigger_cell} = {trigger_value!r}", flush=True)
        if values_match(trigger_value, config.trigger_value):
            handle_trigger(context, config, trigger_value)
            if config.once:
                return
        elif config.once:
            return
        time.sleep(config.poll_seconds)


def main() -> None:
    config = build_config(parse_args())
    try:
        run(config)
    except KeyboardInterrupt:
        print("[DONE] Watcher stopped by user.", flush=True)
    except Exception as exc:
        traceback.print_exc()
        print(f"[ERROR] {exc}", flush=True)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
