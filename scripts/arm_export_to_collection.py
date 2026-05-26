from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env", override=True, encoding="utf-8-sig")

ARM_LOGIN_URL = os.getenv("ARM_LOGIN_URL", "http://192.168.0.187/BPMPlus/#/passport/login")
ARM_RECEIVABLE_URL = os.getenv("ARM_RECEIVABLE_URL", "http://192.168.0.187/BPMPlus/#/arm/armr01")

ARM_ACCOUNT = os.getenv("ARM_ACCOUNT", "108010")
ARM_PASSWORD = os.getenv("ARM_PASSWORD")
ARM_IMPORT_WEBAPP_URL = os.getenv("ARM_IMPORT_WEBAPP_URL") or os.getenv("ARM_WEBAPP_URL")
ARM_WEBAPP_TOKEN = os.getenv("ARM_WEBAPP_TOKEN")
ARM_COLLECTION_SPREADSHEET_ID = (
    os.getenv("ARM_COLLECTION_SPREADSHEET_ID")
    or os.getenv("SPREADSHEET_ID")
    or os.getenv("GOOGLE_SHEET_ID")
)
ARM_COLLECTION_SHEET_NAME = os.getenv("ARM_COLLECTION_SHEET_NAME", "Collection")
ARM_COLLECTION_STATUS_CELL = os.getenv("ARM_COLLECTION_STATUS_CELL", "B1")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

DOWNLOAD_DIR = Path(os.getenv("ARM_DOWNLOAD_DIR", r"C:\ARM_Downloads"))
DEBUG_DIR = Path(os.getenv("ARM_DEBUG_DIR", r"C:\ARM_Debug"))

SOURCE_COLS = [
    '\u5ba2\u6236\u540d\u7a31',
    '\u767c\u7968\u65e5\u671f',
    '\u767c\u7968\u865f\u78bc',
    '\u7d50\u5e33\u55ae\u865f',
    '\u7d50\u5e33\u55ae\u696d\u52d9\u54e1',
    '\u672c\u5e63\u61c9\u6536\u5e33\u6b3e',
    '\u672c\u5e63\u672a\u6536\u91d1\u984d',
]

HEADER_ALIASES = {
    '\u5ba2\u6236\u540d\u7a31': [
        '\u5ba2\u6236\u540d\u7a31',
        '\u5ba2\u6236',
        'Customer Name',
        '\u6470\uff38\uf357?\uf699\u8fc2',
        '\u6470\uff38\uf357',
],
    '\u767c\u7968\u65e5\u671f': [
        '\u767c\u7968\u65e5\u671f',
        '\u65e5\u671f',
        'Invoice Date',
        '?\u6f5b\u5de8?\u4ea4?',
        '?\u4ea4?',
],
    '\u767c\u7968\u865f\u78bc': [
        '\u767c\u7968\u865f\u78bc',
        '\u767c\u7968\u7de8\u865f',
        'Invoice No',
        'Invoice Number',
        '?\u6f5b\u5de8?\uee03\u2163',
        '?\u6f5b\u5de8\u877a\u523b?',
],
    '\u7d50\u5e33\u55ae\u865f': [
        '\u7d50\u5e33\u55ae\u865f',
        '\u7d50\u5e33\u55ae\u7de8\u865f',
        'Closing No',
        '\u876f\ue4ce\u8463?\u682a?',
        '\u876f\ue4ce\u8463?\u6843\u694a??',
],
    '\u7d50\u5e33\u55ae\u696d\u52d9\u54e1': [
        '\u7d50\u5e33\u55ae\u696d\u52d9\u54e1',
        '\u696d\u52d9\u54e1',
        'Sales',
        '\u876f\ue4ce\u8463?\u683c\u5e73?\uea53\ue661',
        '\u7486\u5256???',
],
    '\u672c\u5e63\u61c9\u6536\u5e33\u6b3e': [
        '\u672c\u5e63\u61c9\u6536\u5e33\u6b3e',
        '\u61c9\u6536\u5e33\u6b3e',
        'Receivable',
        '?\u780d\u99b3?\uf424\ue713\u64a3\u55ae\u72e1',
        '?\uf424\ue713\u64a3\u55ae\u72e1',
],
    '\u672c\u5e63\u672a\u6536\u91d1\u984d': [
        '\u672c\u5e63\u672a\u6536\u91d1\u984d',
        '\u672c\u5e63\u672a\u6536\u5e33\u6b3e',
        '\u672a\u6536\u91d1\u984d',
        '\u672a\u6536\u5e33\u6b3e',
        'Unpaid',
        '?\u780d\u99b3?\u82a3\ue713?\ue56f?',
        '?\u780d\u99b3?\u82a3\ue713\u64a3\u55ae\u72e1',
        '?\u82a3\ue713?\ue56f?',
        '?\u82a3\ue713\u64a3\u55ae\u72e1',
],
}


ARM_WEBAPP_ROW_FIELDS = [
    "customer_name",
    "invoice_date",
    "invoice_number",
    "closing_number",
    "sales",
    "receivable_amount",
    "unpaid_amount",
]
ARM_CLOSING_NO_PATTERN = re.compile(r"^61\d{2}-\d{10}$")

def require_env(needs_browser: bool, needs_post: bool, needs_status_cell: bool) -> None:
    missing = []
    if needs_browser and not ARM_PASSWORD:
        missing.append("ARM_PASSWORD")
    if needs_post and not ARM_IMPORT_WEBAPP_URL:
        missing.append("ARM_IMPORT_WEBAPP_URL or ARM_WEBAPP_URL")
    if needs_post and not ARM_WEBAPP_TOKEN:
        missing.append("ARM_WEBAPP_TOKEN")
    if needs_status_cell and not ARM_COLLECTION_SPREADSHEET_ID:
        missing.append("ARM_COLLECTION_SPREADSHEET_ID or SPREADSHEET_ID")
    if needs_status_cell and not SERVICE_ACCOUNT_FILE:
        missing.append("SERVICE_ACCOUNT_FILE or GOOGLE_APPLICATION_CREDENTIALS")
    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))


def setup_driver() -> webdriver.Edge:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    options = EdgeOptions()
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(DOWNLOAD_DIR),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    return webdriver.Edge(options=options)


def save_debug(driver: webdriver.Edge, name: str) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    (DEBUG_DIR / f"{stamp}_{name}.html").write_text(driver.page_source, encoding="utf-8")
    driver.save_screenshot(str(DEBUG_DIR / f"{stamp}_{name}.png"))


def safe_print(*values: Any) -> None:
    text = " ".join(str(value) for value in values)
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace"))


def wait_for_editable_input(driver: webdriver.Edge, wait: WebDriverWait, xpath: str, label: str):
    def find_editable(current_driver):
        for element in current_driver.find_elements(By.XPATH, xpath):
            if not element.is_displayed() or not element.is_enabled():
                continue
            if element.get_attribute("readonly") or element.get_attribute("disabled"):
                continue
            return element
        return False

    return wait.until(find_editable, message=f"Could not find editable {label} input")


def set_input_value(driver: webdriver.Edge, element, value: str) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.2)

    try:
        element.click()
        element.clear()
        element.send_keys(value)
        return
    except Exception:
        pass

    # Angular forms sometimes reject WebDriver clear() when a hidden/mobile
    # duplicate input was present or the control is mid-render. Use the native
    # setter and dispatch input/change so Angular receives the update.
    driver.execute_script(
        """
        const element = arguments[0];
        const value = arguments[1];
        const prototype =
          element instanceof HTMLInputElement
            ? HTMLInputElement.prototype
            : HTMLTextAreaElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
        setter.call(element, value);
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        element,
        value,
    )


def login_arm(driver: webdriver.Edge, wait: WebDriverWait) -> None:
    print("[STEP] Login ARM")
    driver.get(ARM_LOGIN_URL)
    time.sleep(2)
    save_debug(driver, "login_page")

    account_input = wait_for_editable_input(
        driver,
        wait,
        "//input[(@type='text' or not(@type)) and (contains(@placeholder, '帳') or contains(@placeholder, 'Account') or @formcontrolname='userName')]",
        "account",
    )
    password_input = wait_for_editable_input(
        driver,
        wait,
        "//input[(@type='password' or contains(@placeholder, '密') or contains(@placeholder, 'Password') or @formcontrolname='password')]",
        "password",
    )

    set_input_value(driver, account_input, ARM_ACCOUNT)
    set_input_value(driver, password_input, ARM_PASSWORD)

    login_button = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//button[contains(normalize-space(.), '登入')]"
                " | //span[contains(normalize-space(.), '登入')]/ancestor::button[1]",
            )
        )
    )
    login_button.click()
    time.sleep(5)
    save_debug(driver, "after_login")
    print("[OK] Login clicked")


def go_to_arm_receivables(driver: webdriver.Edge, wait: WebDriverWait) -> None:
    print("[STEP] Open ARM receivables page")
    driver.get(ARM_RECEIVABLE_URL)
    time.sleep(5)
    save_debug(driver, "armr01_page")

    detail_xpath = (
        "//span[contains(@class, 'ng-star-inserted') and "
        "(contains(normalize-space(.), '點我觀看明細') or contains(normalize-space(.), '觀看明細'))]"
    )

    try:
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.XPATH, detail_xpath)))
    except TimeoutException:
        print("[STEP] Direct route stayed on home; click ARM receivables menu")
        receivables_menu = wait.until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//a[@data-id='3' or .//span[@title='逾期應收帳款'] or .//span[normalize-space(.)='逾期應收帳款']]",
                )
            )
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", receivables_menu)
        time.sleep(0.5)
        try:
            receivables_menu.click()
        except Exception:
            driver.execute_script("arguments[0].click();", receivables_menu)
        time.sleep(5)
        save_debug(driver, "after_click_receivables_menu")

    print("[STEP] Click 點我觀看明細")
    detail_span = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                detail_xpath,
            )
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", detail_span)
    time.sleep(0.5)

    try:
        detail_span.click()
    except Exception:
        driver.execute_script("arguments[0].click();", detail_span)

    time.sleep(5)
    save_debug(driver, "after_click_detail")
    print("[OK] Detail clicked")


def clear_download_folder() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for file_path in DOWNLOAD_DIR.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in {".xls", ".xlsx", ".crdownload"}:
            file_path.unlink()


def wait_for_download(timeout_seconds: int = 120) -> Path:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        partials = list(DOWNLOAD_DIR.glob("*.crdownload"))
        excels = sorted(
            [p for p in DOWNLOAD_DIR.iterdir() if p.suffix.lower() in {".xls", ".xlsx"}],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if excels and not partials:
            print("[OK] Downloaded:", excels[0])
            return excels[0]
        time.sleep(1)
    raise TimeoutError(f"Excel download did not finish within {timeout_seconds} seconds.")


def export_excel(driver: webdriver.Edge, wait: WebDriverWait) -> Path:
    print("[STEP] Click 匯出Excel")
    clear_download_folder()

    excel_button = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//span[contains(@class, 'hidden-mobile') and contains(normalize-space(.), '匯出Excel')]/ancestor::button[1]",
            )
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", excel_button)
    time.sleep(0.5)

    try:
        excel_button.click()
    except Exception:
        driver.execute_script("arguments[0].click();", excel_button)

    print("[OK] Export Excel clicked")
    return wait_for_download()


def normalize_header(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    normalized = {normalize_header(col): col for col in df.columns}
    resolved = {}
    for required, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            match = normalized.get(normalize_header(alias))
            if match is not None:
                resolved[required] = match
                break
    return resolved


def read_excel_with_header(file_path: Path) -> pd.DataFrame:
    raw = pd.read_excel(file_path, header=None, dtype=str)
    best_row = 0
    best_score = -1
    alias_needles = {normalize_header(alias) for aliases in HEADER_ALIASES.values() for alias in aliases}

    for idx in range(min(len(raw), 20)):
        values = [normalize_header(v) for v in raw.iloc[idx].tolist()]
        score = sum(1 for value in values if value in alias_needles)
        if score > best_score:
            best_score = score
            best_row = idx

    return pd.read_excel(file_path, header=best_row, dtype=str)


def parse_excel_rows(file_path: Path) -> list[list[str]]:
    print("[STEP] Parse Excel:", file_path)
    df = read_excel_with_header(file_path)
    resolved = resolve_columns(df)
    missing = [col for col in SOURCE_COLS if col not in resolved]
    if missing:
        raise RuntimeError(
            "Missing required columns: "
            + ", ".join(missing)
            + "\nActual columns: "
            + ", ".join(str(col) for col in df.columns)
        )

    rows: list[list[str]] = []
    for _, record in df.iterrows():
        row = []
        for col in SOURCE_COLS:
            value = record.get(resolved[col], "")
            if pd.isna(value) or str(value).lower() == "nan":
                value = ""
            row.append(str(value).strip())

        closing_no = row[3]
        if ARM_CLOSING_NO_PATTERN.match(closing_no):
            rows.append(row)

    if not rows:
        raise RuntimeError("No valid ARM rows found. Check closing number format or Excel columns.")

    print(f"[OK] Parsed rows: {len(rows)}")
    safe_print("[FIRST ROW]", json.dumps(rows[0], ensure_ascii=True))
    return rows


def validate_arm_webapp_rows(rows: Any) -> list[list[str]]:
    if not isinstance(rows, list):
        raise ValueError("ARM WebApp rows must be a list.")
    if not rows:
        raise ValueError("ARM WebApp rows must contain at least one row.")

    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            raise ValueError(f"ARM WebApp row {row_number} must be a list.")
        if len(row) != len(ARM_WEBAPP_ROW_FIELDS):
            raise ValueError(
                f"ARM WebApp row {row_number} must have {len(ARM_WEBAPP_ROW_FIELDS)} cells "
                f"({', '.join(ARM_WEBAPP_ROW_FIELDS)}); got {len(row)}."
            )
        non_strings = [field for field, value in zip(ARM_WEBAPP_ROW_FIELDS, row) if not isinstance(value, str)]
        if non_strings:
            raise ValueError(f"ARM WebApp row {row_number} has non-string cells: {', '.join(non_strings)}.")
        closing_number = row[ARM_WEBAPP_ROW_FIELDS.index("closing_number")].strip()
        if not ARM_CLOSING_NO_PATTERN.match(closing_number):
            raise ValueError(
                f"ARM WebApp row {row_number} has invalid closing_number {closing_number!r}; "
                "expected ^61\\d{2}-\\d{10}$."
            )
    return rows


def build_arm_webapp_payload(rows: list[list[str]], token: str | None = None) -> dict[str, Any]:
    webapp_token = ARM_WEBAPP_TOKEN if token is None else token
    if not webapp_token:
        raise ValueError("ARM WebApp token is required.")
    return {
        "token": webapp_token,
        "rows": validate_arm_webapp_rows(rows),
    }


def parse_arm_webapp_response(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise RuntimeError("Apps Script response must be a JSON object.")
    if not result.get("ok"):
        raise RuntimeError("Apps Script error: " + str(result.get("error")))
    return result


def post_rows_to_apps_script(rows: list[list[str]]) -> dict[str, Any]:
    print("[STEP] Send rows to Apps Script")
    payload = build_arm_webapp_payload(rows)
    response = requests.post(
        ARM_IMPORT_WEBAPP_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=120,
    )

    print("[HTTP]", response.status_code)
    safe_print(response.text[:1000])
    response.raise_for_status()
    return parse_arm_webapp_response(response.json())


def build_collection_update_sentence(row_count: int, updated_on: date | None = None) -> str:
    day = updated_on or date.today()
    return f"last update in {day.strftime('%Y/%m/%d')} with {row_count} rows"


def update_collection_status_cell(row_count: int) -> str:
    print("[STEP] Update Collection status cell")
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=credentials)
    status_text = build_collection_update_sentence(row_count)
    write_range = f"{quote_sheet_name(ARM_COLLECTION_SHEET_NAME)}!{ARM_COLLECTION_STATUS_CELL}"
    service.spreadsheets().values().update(
        spreadsheetId=ARM_COLLECTION_SPREADSHEET_ID,
        range=write_range,
        valueInputOption="USER_ENTERED",
        body={"values": [[status_text]]},
    ).execute()
    print(f"[OK] Updated {ARM_COLLECTION_SHEET_NAME}!{ARM_COLLECTION_STATUS_CELL}: {status_text}")
    return status_text


def quote_sheet_name(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def download_from_arm() -> Path:
    driver = setup_driver()
    wait = WebDriverWait(driver, 30)
    try:
        login_arm(driver, wait)
        go_to_arm_receivables(driver, wait)
        return export_excel(driver, wait)
    finally:
        driver.quit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ARM receivables to the Collection sheet.")
    parser.add_argument("--excel", type=Path, help="Use an existing ARM Excel file instead of opening the browser.")
    parser.add_argument("--dry-run", action="store_true", help="Parse rows but do not post them to Apps Script.")
    parser.add_argument(
        "--skip-status-cell",
        action="store_true",
        help="Do not update the Collection status sentence after import.",
    )
    args = parser.parse_args()

    require_env(
        needs_browser=args.excel is None,
        needs_post=not args.dry_run,
        needs_status_cell=False,
    )
    file_path = args.excel or download_from_arm()
    rows = parse_excel_rows(file_path)

    if args.dry_run:
        safe_print(json.dumps({
            "ok": True,
            "dryRunRows": len(rows),
            "statusText": build_collection_update_sentence(len(rows)),
            "firstRow": rows[0],
        }, ensure_ascii=True, indent=2))
        return

    result = post_rows_to_apps_script(rows)
    if not args.skip_status_cell:
        try:
            result["statusText"] = update_collection_status_cell(len(rows))
        except Exception as err:
            result["statusTextError"] = str(err)
            print("[WARN] Collection status cell update failed; import already succeeded.")
            safe_print(str(err))
    print("[DONE] ARM Excel imported to Collection.")
    safe_print(json.dumps(result, ensure_ascii=True, indent=2)[:3000])


if __name__ == "__main__":
    main()

