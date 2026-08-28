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

from app.window_layout import minimize_visible_titled_windows, move_console_to_half_screen, set_console_title

CRM_TRIGGER_VALUE = "work record keyin"
LLM_TRIGGER_VALUE = "LLM>T"
LLM_TARGET_COLUMN = "T,U"
LLM_PROMPT_ROW = 2
LLM_PROMPT = "潤飾PSR日報成專業緊湊的情境"
TRIGGER_VALUE = CRM_TRIGGER_VALUE
RESET_VALUE = "none"
CRM_RUNNING_VALUE_PREFIX = "running crm work record keyin"
LLM_RUNNING_VALUE_PREFIX = "running V work record LLM>T"
ARM_AI_TRIGGER_VALUE = "AI keyin"
ARM_MESH_TRIGGER_VALUE = "mesh operation"
ARM_CHECK_TRIGGER_VALUE = "check out"
ARM_RUNNING_VALUE_PREFIX = "running Collection U1 ARM"
ARM_FAILED_VALUE_PREFIX = "failed Collection U1 ARM"
RUNNING_VALUE_PREFIX = CRM_RUNNING_VALUE_PREFIX
DEFAULT_COMPANY = os.getenv("CRM_COMPANY", "TOP高峰藥品")
DEFAULT_SHEET_TAB = "V"
DEFAULT_TRIGGER_CELL = "T1"
DEFAULT_ARM_SHEET_TAB = "Collection"
DEFAULT_ARM_TRIGGER_CELL = "U1"
DEFAULT_ARM_ROOT = ROOT.parent / "ARM"
ARM_TRIGGER_BATCHES = {
    ARM_AI_TRIGGER_VALUE: Path("automations") / "run_checked_remittances.bat",
    ARM_MESH_TRIGGER_VALUE: Path("automations") / "run_checked_remittances_mesh.bat",
    ARM_CHECK_TRIGGER_VALUE: Path("automations") / "run_checked_check_remittances.bat",
}
OUTPUT_DIR = ROOT / "data" / "crm_work_record_trigger"
SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CRM_WATCHER_CLI_WINDOW_TITLE = os.getenv("CRM_WATCHER_CLI_WINDOW_TITLE", "CRM Work Record Watch")


@dataclass(frozen=True)
class TriggerConfig:
    sheet_tab: str
    trigger_cell: str
    trigger_value: str
    reset_value: str
    running_value_prefix: str
    poll_seconds: int
    once: bool
    probe: bool
    dry_run: bool
    company: str
    date: str
    max_rows: int
    start_row: int
    llm_trigger_value: str
    llm_max_rows: int
    llm_latest: bool
    llm_target_column: str
    llm_prompt_row: int
    llm_prompt: str
    keep_open: bool
    watch_arm: bool
    arm_sheet_tab: str
    arm_trigger_cell: str
    arm_root: Path


@dataclass(frozen=True)
class SheetContext:
    service: Any
    spreadsheet_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Watch a Google Sheets dropdown cell and dispatch CRM key-in or "
            "V work-record Ollama polish jobs when it is set to a trigger value."
        )
    )
    parser.add_argument("--sheet-tab", default=DEFAULT_SHEET_TAB, help="Trigger sheet tab. Default: V.")
    parser.add_argument("--trigger-cell", default=DEFAULT_TRIGGER_CELL, help="Trigger cell. Default: T1.")
    parser.add_argument(
        "--trigger-value",
        default="",
        help="Dropdown value that starts CRM key-in. Default: work record keyin.",
    )
    parser.add_argument("--reset-value", default=RESET_VALUE, help="Value to write after a run. Default: none.")
    parser.add_argument(
        "--running-value-prefix",
        default=RUNNING_VALUE_PREFIX,
        help="Non-trigger value written before CRM starts. Default: running crm work record keyin.",
    )
    parser.add_argument("--poll-seconds", type=int, default=15, help="Watch interval. Default: 15.")
    parser.add_argument("--once", action="store_true", help="Check once, then exit.")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Read and report the trigger state without logging, resetting, or running CRM. Implies --once.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print/log the intended command without running CRM.")
    parser.add_argument("--company", default=DEFAULT_COMPANY, help="CRM company visible text.")
    parser.add_argument("--date", default="", help="Optional CRM sheet date override, e.g. 2026/5/29.")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional CRM max rows. 0 means all matching rows.")
    parser.add_argument("--start-row", type=int, default=0, help="Only load CRM sheet rows at or after this row.")
    parser.add_argument(
        "--llm-trigger-value",
        default=LLM_TRIGGER_VALUE,
        help="Dropdown value that starts V!T Ollama polish. Default: LLM>T.",
    )
    parser.add_argument(
        "--llm-max-rows",
        type=int,
        default=0,
        help="Maximum V!T rows to edit for LLM>T. Default: 0 means all matching rows.",
    )
    parser.add_argument(
        "--llm-earliest",
        dest="llm_latest",
        action="store_false",
        default=True,
        help="For LLM>T, process earliest matching row instead of latest.",
    )
    parser.add_argument(
        "--llm-target-column",
        default=LLM_TARGET_COLUMN,
        help="Column(s) written by LLM>T. Default: T,U.",
    )
    parser.add_argument(
        "--llm-prompt-row",
        type=int,
        default=LLM_PROMPT_ROW,
        help="Prompt row used by LLM>T target columns. Default: 2.",
    )
    parser.add_argument(
        "--llm-prompt",
        default=LLM_PROMPT,
        help="Prompt instruction passed to the V work-record editor.",
    )
    parser.add_argument("--keep-open", action="store_true", help="Pass --keep-open to the CRM browser run.")
    parser.add_argument(
        "--no-arm-watch",
        action="store_true",
        help="Do not monitor Collection!U1 for ARM remittance batch triggers.",
    )
    parser.add_argument("--arm-sheet-tab", default=DEFAULT_ARM_SHEET_TAB, help="ARM trigger sheet tab. Default: Collection.")
    parser.add_argument("--arm-trigger-cell", default=DEFAULT_ARM_TRIGGER_CELL, help="ARM trigger cell. Default: U1.")
    parser.add_argument(
        "--arm-root",
        default=str(DEFAULT_ARM_ROOT),
        help="ARM project root containing automations/*.bat. Default: sibling C:\\Dev\\ARM.",
    )
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
        trigger_value=args.trigger_value or CRM_TRIGGER_VALUE,
        reset_value=args.reset_value,
        running_value_prefix=args.running_value_prefix,
        poll_seconds=max(1, args.poll_seconds),
        once=args.once or args.probe,
        probe=args.probe,
        dry_run=args.dry_run,
        company=args.company,
        date=args.date,
        max_rows=max(0, args.max_rows),
        start_row=max(0, args.start_row),
        llm_trigger_value=args.llm_trigger_value,
        llm_max_rows=max(0, args.llm_max_rows),
        llm_latest=args.llm_latest,
        llm_target_column=args.llm_target_column,
        llm_prompt_row=max(0, args.llm_prompt_row),
        llm_prompt=args.llm_prompt,
        keep_open=args.keep_open,
        watch_arm=not args.no_arm_watch,
        arm_sheet_tab=args.arm_sheet_tab,
        arm_trigger_cell=args.arm_trigger_cell,
        arm_root=Path(args.arm_root),
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


def read_cell_value(context: SheetContext, sheet_tab: str, cell: str) -> str:
    values = get_values(context, sheet_range(sheet_tab, cell))
    return str(values[0][0] if values and values[0] else "").strip()


def read_trigger_value(context: SheetContext, config: TriggerConfig) -> str:
    return read_cell_value(context, config.sheet_tab, config.trigger_cell)


def update_cell_value(context: SheetContext, sheet_tab: str, cell: str, value: str) -> None:
    update_values(context, sheet_range(sheet_tab, cell), [[value]])


def reset_trigger_value(context: SheetContext, config: TriggerConfig) -> None:
    update_cell_value(context, config.sheet_tab, config.trigger_cell, config.reset_value)


def running_trigger_value(config: TriggerConfig, running_value_prefix: str | None = None) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"{running_value_prefix or config.running_value_prefix} {stamp}"


def claim_trigger_value(
    context: SheetContext,
    config: TriggerConfig,
    observed_value: str,
    *,
    expected_value: str | None = None,
    running_value_prefix: str | None = None,
    job_label: str = "CRM",
) -> str | None:
    expected = expected_value or config.trigger_value
    current_value = read_trigger_value(context, config)
    if not values_match(current_value, expected):
        print(
            f"[SKIP] {config.sheet_tab}!{config.trigger_cell} changed from "
            f"{observed_value!r} to {current_value!r}; {job_label} was not started.",
            flush=True,
        )
        return None

    claimed_value = running_trigger_value(config, running_value_prefix)
    update_values(context, sheet_range(config.sheet_tab, config.trigger_cell), [[claimed_value]])
    print(
        f"[OK] Claimed {config.sheet_tab}!{config.trigger_cell}: "
        f"{expected!r} -> {claimed_value!r}",
        flush=True,
    )
    return claimed_value


def running_cell_value(prefix: str, trigger_value: str) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"{prefix} {trigger_value} {stamp}"


def claim_cell_value(
    context: SheetContext,
    *,
    sheet_tab: str,
    cell: str,
    observed_value: str,
    expected_value: str,
    running_value_prefix: str,
    job_label: str,
) -> str | None:
    current_value = read_cell_value(context, sheet_tab, cell)
    if not values_match(current_value, expected_value):
        print(
            f"[SKIP] {sheet_tab}!{cell} changed from {observed_value!r} "
            f"to {current_value!r}; {job_label} was not started.",
            flush=True,
        )
        return None

    claimed_value = running_cell_value(running_value_prefix, expected_value)
    update_cell_value(context, sheet_tab, cell, claimed_value)
    print(
        f"[OK] Claimed {sheet_tab}!{cell}: {expected_value!r} -> {claimed_value!r}",
        flush=True,
    )
    return claimed_value


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
    if config.start_row:
        command.extend(["--start-row", str(config.start_row)])
    if config.keep_open:
        command.append("--keep-open")
    return command


def build_llm_command(config: TriggerConfig, *, writeback: bool = True) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "v_work_record_polish.py"),
        "--target-column",
        config.llm_target_column,
        "--prompt",
        config.llm_prompt,
    ]
    if config.llm_prompt_row:
        command.extend(["--prompt-row", str(config.llm_prompt_row)])
    if config.llm_max_rows == 0:
        command.append("--all")
    else:
        command.extend(["--max-rows", str(config.llm_max_rows)])
    if config.date:
        command.extend(["--date", config.date])
    if config.llm_max_rows != 0 and config.llm_latest:
        command.append("--latest")
    if writeback:
        command.append("--writeback")
    return command


def arm_trigger_option(value: str) -> str:
    for option in ARM_TRIGGER_BATCHES:
        if values_match(value, option):
            return option
    return ""


def resolve_arm_batch(config: TriggerConfig, trigger_value: str) -> Path:
    option = arm_trigger_option(trigger_value)
    if not option:
        raise RuntimeError(f"Unknown ARM trigger value: {trigger_value!r}")
    return config.arm_root / ARM_TRIGGER_BATCHES[option]


def build_arm_command(config: TriggerConfig, trigger_value: str) -> list[str]:
    batch_path = resolve_arm_batch(config, trigger_value)
    if os.name == "nt":
        return ["cmd.exe", "/c", str(batch_path)]
    return [str(batch_path)]


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


def output_log_path(prefix: str = "crm_work_record_lookup") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"{prefix}_{stamp}.log"


def child_process_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONUTF8", "1")
    return env


def run_command(
    config: TriggerConfig,
    command: list[str],
    *,
    log_prefix: str,
    label: str,
    cwd: Path = ROOT,
) -> tuple[int, Path, str]:
    log_path = output_log_path(log_prefix)
    command_text = subprocess.list2cmdline(command)
    if config.dry_run:
        output = f"[DRY-RUN] {command_text}\n"
        log_path.write_text(output, encoding="utf-8")
        print(output, end="")
        return 0, log_path, output

    print(f"[STEP] Running {label} command: {command_text}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_process_env(),
    )
    output_parts: list[str] = []
    if process.stdout is not None:
        for line in process.stdout:
            output_parts.append(line)
            print(line, end="", flush=True)
    return_code = process.wait()
    output = "".join(output_parts)
    log_path.write_text(output, encoding="utf-8")
    return return_code, log_path, output


def run_arm_batch(config: TriggerConfig, trigger_value: str) -> tuple[int, Path, str]:
    batch_path = resolve_arm_batch(config, trigger_value)
    if not batch_path.exists():
        raise RuntimeError(f"Missing ARM batch file: {batch_path}")
    log_path = output_log_path("arm_collection_u1")
    command = build_arm_command(config, trigger_value)
    command_text = subprocess.list2cmdline(command)
    if config.dry_run:
        output = f"[DRY-RUN] {command_text}\n"
        log_path.write_text(output, encoding="utf-8")
        print(output, end="", flush=True)
        return 0, log_path, output

    started = datetime.now().isoformat(timespec="seconds")
    print(f"[STEP] Running ARM {trigger_value} command: {command_text}", flush=True)
    print("[STEP] ARM batch output is attached to this watcher window.", flush=True)
    completed = subprocess.run(command, cwd=config.arm_root)
    ended = datetime.now().isoformat(timespec="seconds")
    output = (
        f"command={command_text}\n"
        f"cwd={config.arm_root}\n"
        f"started={started}\n"
        f"ended={ended}\n"
        f"return_code={completed.returncode}\n"
    )
    log_path.write_text(output, encoding="utf-8")
    return completed.returncode, log_path, output


def run_crm(config: TriggerConfig) -> tuple[int, Path, str]:
    set_console_title(CRM_WATCHER_CLI_WINDOW_TITLE)
    minimize_visible_titled_windows()
    if move_console_to_half_screen(
        "worker",
        title_text=CRM_WATCHER_CLI_WINDOW_TITLE,
        fallback_to_console_window=False,
    ):
        print("[OK] Twinplay watcher CLI placed on the right half.", flush=True)
    else:
        print(
            "[WARN] Twinplay watcher CLI window was not found by visible title; "
            "console remains at current position.",
            flush=True,
        )
    return run_command(
        config,
        build_crm_command(config),
        log_prefix="crm_work_record_lookup",
        label="CRM",
    )


def run_llm_polish(config: TriggerConfig) -> tuple[int, Path, str]:
    return run_command(
        config,
        build_llm_command(config, writeback=not config.dry_run),
        log_prefix="v_work_record_polish",
        label="V work-record polish",
    )


def output_summary(output: str) -> dict[str, Any]:
    loaded_match = re.search(r"Loaded\s+(\d+)\s+sheet row", output)
    saved_rows = re.findall(r"Save record:\s+sheet row\s+(\d+)", output)
    updated_match = re.search(r"Updated\s+(\d+)\s+V(?:![A-Z]+)?\s*target\s+cell", output)
    prepared_match = re.search(r"Rows prepared:\s+(\d+)", output)
    return {
        "loaded_rows": int(loaded_match.group(1)) if loaded_match else None,
        "saved_sheet_rows": saved_rows,
        "prepared_rows": int(prepared_match.group(1)) if prepared_match else None,
        "updated_cells": int(updated_match.group(1)) if updated_match else None,
    }


def print_probe(context: SheetContext, config: TriggerConfig, trigger_value: str) -> None:
    crm_command = build_crm_command(config)
    llm_command = build_llm_command(config, writeback=True)
    arm_value = read_cell_value(context, config.arm_sheet_tab, config.arm_trigger_cell) if config.watch_arm else ""
    crm_armed = values_match(trigger_value, config.trigger_value)
    llm_armed = values_match(trigger_value, config.llm_trigger_value)
    arm_option = arm_trigger_option(arm_value)
    print("[PROBE] Read-only trigger proof; no log, reset, or job command will run.", flush=True)
    print(f"[PROBE] Spreadsheet ID: {context.spreadsheet_id}", flush=True)
    print(f"[PROBE] Trigger cell: {config.sheet_tab}!{config.trigger_cell}", flush=True)
    print(f"[PROBE] Current value: {trigger_value!r}", flush=True)
    print(f"[PROBE] CRM armed ({config.trigger_value!r}): {crm_armed}", flush=True)
    print(f"[PROBE] LLM armed ({config.llm_trigger_value!r}): {llm_armed}", flush=True)
    print(f"[PROBE] Intended CRM command: {subprocess.list2cmdline(crm_command)}", flush=True)
    print(f"[PROBE] Intended LLM command: {subprocess.list2cmdline(llm_command)}", flush=True)
    if config.watch_arm:
        print(f"[PROBE] ARM trigger cell: {config.arm_sheet_tab}!{config.arm_trigger_cell}", flush=True)
        print(f"[PROBE] ARM current value: {arm_value!r}", flush=True)
        print(
            f"[PROBE] ARM armed ({ARM_AI_TRIGGER_VALUE!r}/{ARM_MESH_TRIGGER_VALUE!r}/{ARM_CHECK_TRIGGER_VALUE!r}): "
            f"{bool(arm_option)}",
            flush=True,
        )
        if arm_option:
            print(
                f"[PROBE] Intended ARM command: {subprocess.list2cmdline(build_arm_command(config, arm_option))}",
                flush=True,
            )
    print(
        f"[PROBE] Live/dry-run consume would first write a non-trigger "
        f"running value, then finish with {config.reset_value!r}.",
        flush=True,
    )


def handle_job_trigger(
    context: SheetContext,
    config: TriggerConfig,
    trigger_value: str,
    *,
    expected_value: str,
    running_value_prefix: str,
    command: list[str],
    run_job: Any,
    operation: str,
    start_purpose: str,
    finish_purpose: str,
    job_label: str,
) -> None:
    claimed_value = claim_trigger_value(
        context,
        config,
        trigger_value,
        expected_value=expected_value,
        running_value_prefix=running_value_prefix,
        job_label=job_label,
    )
    if claimed_value is None:
        return

    base_variables = {
        "sheet_tab": config.sheet_tab,
        "trigger_cell": config.trigger_cell,
        "trigger_value": trigger_value,
        "reset_value": config.reset_value,
        "claimed_value": claimed_value,
        "command": subprocess.list2cmdline(command),
        "dry_run": config.dry_run,
        "job": job_label,
    }

    return_code = 1
    log_path = Path()
    output = ""
    reset_result = "not attempted"
    run_error: Exception | None = None
    try:
        append_log(
            context,
            config,
            operation=operation,
            result="started",
            purpose=start_purpose,
            variables=base_variables,
        )
        return_code, log_path, output = run_job(config)
    except Exception as exc:
        run_error = exc
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
        operation=operation,
        result=result,
        purpose=finish_purpose,
        variables=variables,
        details=str(log_path) if log_path else "",
    )
    if run_error is not None:
        raise run_error
    if return_code != 0:
        raise RuntimeError(f"{job_label} command failed with exit code {return_code}. See {log_path}")


def handle_trigger(context: SheetContext, config: TriggerConfig, trigger_value: str) -> None:
    handle_job_trigger(
        context,
        config,
        trigger_value,
        expected_value=config.trigger_value,
        running_value_prefix=config.running_value_prefix,
        command=build_crm_command(config),
        run_job=run_crm,
        operation="crm-work-record-keyin-trigger",
        start_purpose="Sheet V dropdown triggered CRM work record key-in.",
        finish_purpose="CRM work record key-in completed from Sheet V dropdown.",
        job_label="CRM",
    )


def handle_llm_trigger(context: SheetContext, config: TriggerConfig, trigger_value: str) -> None:
    handle_job_trigger(
        context,
        config,
        trigger_value,
        expected_value=config.llm_trigger_value,
        running_value_prefix=LLM_RUNNING_VALUE_PREFIX,
        command=build_llm_command(config, writeback=not config.dry_run),
        run_job=run_llm_polish,
        operation="v-work-record-polish-trigger",
        start_purpose="Sheet V dropdown triggered local Ollama editor for V work records.",
        finish_purpose="Local Ollama editor for V work records completed from Sheet V dropdown.",
        job_label="V work-record polish",
    )


def handle_arm_trigger(context: SheetContext, config: TriggerConfig, trigger_value: str) -> None:
    option = arm_trigger_option(trigger_value)
    if not option:
        raise RuntimeError(f"Unsupported ARM trigger value: {trigger_value!r}")

    claimed_value = claim_cell_value(
        context,
        sheet_tab=config.arm_sheet_tab,
        cell=config.arm_trigger_cell,
        observed_value=trigger_value,
        expected_value=option,
        running_value_prefix=ARM_RUNNING_VALUE_PREFIX,
        job_label=f"ARM {option}",
    )
    if claimed_value is None:
        return

    command = build_arm_command(config, option)
    base_variables = {
        "sheet_tab": config.arm_sheet_tab,
        "trigger_cell": config.arm_trigger_cell,
        "trigger_value": trigger_value,
        "reset_value": config.reset_value,
        "claimed_value": claimed_value,
        "command": subprocess.list2cmdline(command),
        "dry_run": config.dry_run,
        "job": f"ARM {option}",
    }

    return_code = 1
    log_path = Path()
    output = ""
    reset_result = "not attempted"
    run_error: Exception | None = None
    try:
        append_log(
            context,
            config,
            operation="arm-collection-u1-trigger",
            result="started",
            purpose="Collection U1 dropdown triggered local ARM remittance batch.",
            variables=base_variables,
        )
        return_code, log_path, output = run_arm_batch(config, option)
    except Exception as exc:
        run_error = exc
    finally:
        if return_code == 0:
            try:
                update_cell_value(context, config.arm_sheet_tab, config.arm_trigger_cell, config.reset_value)
                reset_result = "reset"
                print(
                    f"[OK] Reset {config.arm_sheet_tab}!{config.arm_trigger_cell} to {config.reset_value}",
                    flush=True,
                )
            except Exception as exc:
                reset_result = f"reset failed: {exc}"
                print(f"[WARN] {reset_result}", flush=True)
        else:
            failed_value = running_cell_value(ARM_FAILED_VALUE_PREFIX, option)
            try:
                update_cell_value(context, config.arm_sheet_tab, config.arm_trigger_cell, failed_value)
                reset_result = f"marked failed: {failed_value}"
            except Exception as exc:
                reset_result = f"failed marker write failed: {exc}"
            print(
                f"[WARN] {config.arm_sheet_tab}!{config.arm_trigger_cell} was not reset because ARM returned {return_code}.",
                flush=True,
            )

    result = "success" if return_code == 0 else "error"
    append_log(
        context,
        config,
        operation="arm-collection-u1-trigger",
        result=result,
        purpose="Local ARM remittance batch completed from Collection U1 dropdown.",
        variables={
            **base_variables,
            "return_code": return_code,
            "output_log": str(log_path) if log_path else "",
            "trigger_reset": reset_result,
            **output_summary(output),
        },
        details=str(log_path) if log_path else "",
    )
    if run_error is not None:
        raise run_error
    if return_code != 0:
        raise RuntimeError(f"ARM {option} command failed with exit code {return_code}. See {log_path}")


def run(config: TriggerConfig) -> None:
    context = open_sheet_context()
    mode = "PROBE" if config.probe else "WATCH"
    print(
        f"[{mode}] {config.sheet_tab}!{config.trigger_cell} triggers: "
        f"{config.trigger_value!r}=CRM key-in, {config.llm_trigger_value!r}=V!T to V!{config.llm_target_column} LLM edit; "
        f"reset value is {config.reset_value!r}.",
        flush=True,
    )
    if config.watch_arm:
        print(
            f"[{mode}] {config.arm_sheet_tab}!{config.arm_trigger_cell} triggers: "
            f"{ARM_AI_TRIGGER_VALUE!r}=normal remittances, "
            f"{ARM_MESH_TRIGGER_VALUE!r}=ARM mesh, "
            f"{ARM_CHECK_TRIGGER_VALUE!r}=check remittances; "
            f"reset on success is {config.reset_value!r}.",
            flush=True,
        )
    while True:
        trigger_value = read_trigger_value(context, config)
        print(f"[CHECK] {config.sheet_tab}!{config.trigger_cell} = {trigger_value!r}", flush=True)
        arm_value = ""
        if config.watch_arm:
            arm_value = read_cell_value(context, config.arm_sheet_tab, config.arm_trigger_cell)
            print(f"[CHECK] {config.arm_sheet_tab}!{config.arm_trigger_cell} = {arm_value!r}", flush=True)
        if config.probe:
            print_probe(context, config, trigger_value)
            return
        if values_match(trigger_value, config.trigger_value):
            handle_trigger(context, config, trigger_value)
            if config.once:
                return
        elif values_match(trigger_value, config.llm_trigger_value):
            handle_llm_trigger(context, config, trigger_value)
            if config.once:
                return
        elif config.watch_arm and arm_trigger_option(arm_value):
            handle_arm_trigger(context, config, arm_value)
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
