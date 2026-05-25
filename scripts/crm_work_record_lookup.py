from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from selenium import webdriver
from selenium.common.exceptions import (
    NoAlertPresentException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


DEFAULT_INPUT = {
    "crmUrl": "http://192.168.0.250/WebCRM/src/_Common/AppUtil/FrameSet/Newlogin.aspx",
    "account": "108010",
    "password": "28521017",
    "company": "TOP高峰藥品",
    "customerName": "中崙",
    "resultSelection": "first",
}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
DEFAULT_TEST_WORK_NATURE = "39003　　新資料提供"


@dataclass(frozen=True)
class RunConfig:
    crm_url: str
    account: str
    password: str
    company: str | None
    customer_name: str
    result_selection: str
    browser: str
    keep_open: bool
    from_sheet_v: bool
    sheet_date: str
    sheet_tab: str
    skip_test_record: bool
    max_rows: int


@dataclass(frozen=True)
class WorkRecord:
    source_lookup_key: str
    work_nature: str = ""
    record_content: str = ""
    sheet_row: int | None = None


def safe_print(*values: Any) -> None:
    text = " ".join(str(value) for value in values)
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="replace").decode(encoding), flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Open CRM 工作記錄維護, create/use a new work record, search 來源代號 by "
            "客戶名稱, and select the first result."
        )
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        help="Optional JSON file. Keys match crmUrl/account/password/company/customerName/resultSelection.",
    )
    parser.add_argument("--company", default=None, help="Override company visible text or option value.")
    parser.add_argument("--customer-name", default=None, help="Override customerName. Default: 中崙")
    parser.add_argument("--browser", choices=["chrome", "edge"], default="chrome")
    parser.add_argument(
        "--from-sheet-v",
        action="store_true",
        help="After the test record, load rows from the configured workbook sheet V.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Sheet date filter for column H. Defaults to today in Asia/Taipei, e.g. 2026/5/26.",
    )
    parser.add_argument("--sheet-tab", default="V", help="Source sheet tab. Default: V.")
    parser.add_argument(
        "--skip-test-record",
        action="store_true",
        help="Skip the standalone customerName test record and only process sheet rows.",
    )
    parser.add_argument("--max-rows", type=int, default=0, help="Limit sheet rows. 0 means all matches.")
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Leave the browser open after the automation stops.",
    )
    parser.add_argument(
        "--debug-controls",
        action="store_true",
        help="Open the CRM module and print visible form controls, then stop.",
    )
    parser.add_argument(
        "--debug-dialog",
        action="store_true",
        help="Open the 來源代號 lookup dialog and print its visible controls, then stop.",
    )
    parser.add_argument(
        "--debug-dialog-button",
        default="FI024_btn",
        help="Lookup button id to open with --debug-dialog. Default: FI024_btn.",
    )
    parser.add_argument(
        "--debug-dialog-after-source",
        action="store_true",
        help="With --debug-dialog, first fill customerName as 來源代號 before opening the debug lookup.",
    )
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> RunConfig:
    payload = dict(DEFAULT_INPUT)
    if args.input_json:
        with args.input_json.open("r", encoding="utf-8") as fh:
            payload.update(json.load(fh))
    if args.company:
        payload["company"] = args.company
    if args.customer_name:
        payload["customerName"] = args.customer_name

    return RunConfig(
        crm_url=str(payload["crmUrl"]),
        account=str(payload["account"]),
        password=str(payload["password"]),
        company=payload.get("company") or None,
        customer_name=str(payload["customerName"]),
        result_selection=str(payload.get("resultSelection") or "first"),
        browser=args.browser,
        keep_open=args.keep_open,
        from_sheet_v=args.from_sheet_v,
        sheet_date=normalize_date_text(args.date or today_taipei_text()),
        sheet_tab=args.sheet_tab,
        skip_test_record=args.skip_test_record,
        max_rows=args.max_rows,
    )


def today_taipei_text() -> str:
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    return f"{now.year}/{now.month}/{now.day}"


def normalize_date_text(value: str) -> str:
    text = str(value or "").strip()
    if "-" in text:
        parts = text.split("-")
    else:
        parts = text.split("/")
    if len(parts) == 3 and all(part.strip().isdigit() for part in parts):
        year, month, day = (int(part.strip()) for part in parts)
        return f"{year}/{month}/{day}"
    return text


def build_driver(config: RunConfig) -> WebDriver:
    if config.browser == "edge":
        options = webdriver.EdgeOptions()
        options.add_argument("--start-maximized")
        return webdriver.Edge(options=options)

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    return webdriver.Chrome(options=options)


def wait(driver: WebDriver, seconds: int = 20) -> WebDriverWait:
    return WebDriverWait(driver, seconds)


def switch_default(driver: WebDriver) -> None:
    driver.switch_to.default_content()


def switch_to_frame(driver: WebDriver, by: By, value: str, seconds: int = 20) -> None:
    switch_default(driver)
    wait(driver, seconds).until(EC.frame_to_be_available_and_switch_to_it((by, value)))


def switch_to_work_frame(driver: WebDriver) -> None:
    switch_to_frame(driver, By.NAME, "main")
    iframe = wait(driver, 20).until(
        lambda d: next(
            (
                frame
                for frame in d.find_elements(By.CSS_SELECTOR, "iframe")
                if "SALI21" in (frame.get_attribute("src") or "")
            ),
            None,
        )
    )
    driver.switch_to.frame(iframe)


def login(driver: WebDriver, config: RunConfig) -> None:
    safe_print("[STEP] Open CRM login page")
    driver.get(config.crm_url)

    if "TreeMainFrame.aspx" in driver.current_url:
        safe_print("[OK] Already logged in")
        return

    if config.company:
        company_select = Select(driver.find_element(By.ID, "DropDownList1"))
        try:
            company_select.select_by_visible_text(config.company)
        except Exception:
            company_select.select_by_value(config.company)

    account = wait(driver, 20).until(EC.element_to_be_clickable((By.ID, "TextBox1")))
    account.clear()
    account.send_keys(config.account)

    password = driver.find_element(By.ID, "TextBox2")
    password.clear()
    password.send_keys(config.password)
    driver.find_element(By.ID, "ImageButton1").click()

    wait(driver, 30).until(lambda d: "TreeMainFrame.aspx" in d.current_url)
    safe_print("[OK] Logged in")


def open_work_record_maintenance(driver: WebDriver) -> None:
    safe_print("[STEP] Open 工作記錄維護")
    switch_to_frame(driver, By.NAME, "banner")
    wait(driver, 20).until(EC.element_to_be_clickable((By.ID, "Btn_1"))).click()

    switch_to_work_frame(driver)
    wait(driver, 20).until(lambda d: "工作記錄維護作業" in d.find_element(By.TAG_NAME, "body").text)
    safe_print("[OK] 工作記錄維護 is open")


def ensure_new_record(driver: WebDriver) -> None:
    """Click 新增 when needed, then verify 來源代號 lookup is enabled."""
    switch_to_work_frame(driver)
    wait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    source_button = driver.find_elements(By.ID, "FI024_btn")
    if source_button and is_old_crm_button_enabled(source_button[0]):
        safe_print("[OK] Work-record form is already in new/edit mode")
    else:
        add_button = wait(driver, 20).until(EC.element_to_be_clickable((By.ID, "BtnAdd")))
        safe_print("[STEP] Click 新增")
        add_button.click()
        time.sleep(1)
        switch_to_work_frame(driver)

    wait(driver, 20).until(
        lambda d: (
            d.find_elements(By.ID, "FI024_btn")
            and d.find_element(By.ID, "FI024_btn").is_displayed()
            and is_old_crm_button_enabled(d.find_element(By.ID, "FI024_btn"))
        )
    )
    body_text = driver.find_element(By.TAG_NAME, "body").text
    if "來源代號" not in body_text or "工作代號" not in body_text:
        raise RuntimeError("Work-record form did not load the expected fields.")
    safe_print("[OK] Work-record form is ready")


def is_old_crm_button_enabled(element: WebElement) -> bool:
    disabled = element.get_attribute("disabled")
    style = (element.get_attribute("style") or "").replace(" ", "").lower()
    return disabled in (None, "", "false") and "pointer-events:none" not in style


def dump_visible_work_controls(driver: WebDriver) -> None:
    switch_to_work_frame(driver)
    controls = driver.execute_script(
        r"""
        return Array.from(document.querySelectorAll('input,select,img,button,a,textarea'))
          .map((el, i) => {
            const r = el.getBoundingClientRect();
            return {
              i,
              tag: el.tagName,
              id: el.id || null,
              name: el.getAttribute('name'),
              type: el.getAttribute('type'),
              value: el.value || el.getAttribute('value'),
              title: el.getAttribute('title'),
              alt: el.getAttribute('alt'),
              src: el.getAttribute('src'),
              onclick: el.getAttribute('onclick'),
              disabled: !!el.disabled || el.getAttribute('disabled'),
              readonly: !!el.readOnly || el.getAttribute('readonly'),
              text: (el.innerText || el.textContent || '').trim(),
              x: Math.round(r.x),
              y: Math.round(r.y),
              w: Math.round(r.width),
              h: Math.round(r.height),
              visible: r.width > 0 && r.height > 0
            };
          })
          .filter(c => c.visible && (c.id || c.name || c.value || c.title || c.alt || c.onclick || c.text));
        """
    )
    safe_print(json.dumps(controls, ensure_ascii=False, indent=2))


def dump_visible_dialog_controls(driver: WebDriver) -> None:
    switch_to_lookup_dialog_frame(driver)
    payload = driver.execute_script(
        r"""
        const bodyText = document.body ? document.body.innerText : '';
        const controls = Array.from(document.querySelectorAll('input,select,img,button,a,textarea,table,tr,td'))
          .map((el, i) => {
            const r = el.getBoundingClientRect();
            return {
              i,
              tag: el.tagName,
              id: el.id || null,
              name: el.getAttribute('name'),
              type: el.getAttribute('type'),
              value: el.value || el.getAttribute('value'),
              title: el.getAttribute('title'),
              alt: el.getAttribute('alt'),
              onclick: el.getAttribute('onclick'),
              disabled: !!el.disabled || el.getAttribute('disabled'),
              readonly: !!el.readOnly || el.getAttribute('readonly'),
              text: (el.innerText || el.textContent || '').trim().slice(0, 120),
              x: Math.round(r.x),
              y: Math.round(r.y),
              w: Math.round(r.width),
              h: Math.round(r.height),
              visible: r.width > 0 && r.height > 0
            };
          })
          .filter(c => c.visible && (c.tag !== 'TD' || c.text) && (c.id || c.name || c.value || c.title || c.alt || c.onclick || c.text));
        return { bodyText, controls };
        """
    )
    safe_print(json.dumps(payload, ensure_ascii=False, indent=2))


def find_source_lookup_icon(driver: WebDriver) -> WebElement:
    switch_to_work_frame(driver)
    return wait_enabled_old_crm_button(driver, "FI024_btn")


def wait_enabled_old_crm_button(driver: WebDriver, element_id: str) -> WebElement:
    def enabled_button(d: WebDriver) -> WebElement | bool:
        try:
            element = d.find_element(By.ID, element_id)
            return element if is_old_crm_button_enabled(element) else False
        except StaleElementReferenceException:
            return False

    return wait(driver, 20).until(enabled_button)


def open_source_lookup(driver: WebDriver) -> None:
    safe_print("[STEP] Open 來源代號 lookup")
    icon = find_source_lookup_icon(driver)
    driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", icon)
    time.sleep(0.3)
    icon.click()
    switch_to_lookup_dialog_frame(driver)
    wait(driver, 20).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "select")) >= 2)
    safe_print("[OK] Lookup dialog is open")


def switch_to_lookup_dialog_frame(driver: WebDriver) -> None:
    switch_to_work_frame(driver)
    iframe = wait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "iframe#dialogIframe"))
    )
    driver.switch_to.frame(iframe)


def get_lookup_selects(driver: WebDriver) -> list[WebElement]:
    return [
        select
        for select in driver.find_elements(By.CSS_SELECTOR, "select")
        if select.is_displayed() and select.is_enabled()
    ]


def set_lookup_condition(driver: WebDriver) -> WebElement:
    return set_lookup_condition_text(driver, "客戶名稱")


def set_lookup_condition_text(driver: WebDriver, visible_text: str) -> WebElement:
    condition = wait(driver, 10).until(EC.presence_of_element_located((By.ID, "ddlSEARCH")))
    select = Select(condition)
    try:
        select.select_by_visible_text(visible_text)
    except Exception:
        safe_print(f"[WARN] Lookup condition {visible_text!r} not available; using current dropdown value")

    selected = Select(condition).first_selected_option.text.strip()
    if selected != visible_text:
        safe_print(f"[WARN] Lookup condition is {selected!r}, expected {visible_text!r}")
    return condition


def search_customer(driver: WebDriver, customer_name: str) -> None:
    safe_print(f"[STEP] Search customer name: {customer_name}")
    switch_to_lookup_dialog_frame(driver)
    set_lookup_condition(driver)

    search_input = wait(driver, 10).until(EC.element_to_be_clickable((By.ID, "txtSEARCH")))
    search_input.clear()
    search_input.send_keys(customer_name)

    driver.execute_script("okClick('btnSEARCH');")
    wait(driver, 20).until(
        lambda d: customer_name in d.find_element(By.TAG_NAME, "body").text
        or len(visible_result_rows(d, customer_name)) > 0
    )
    safe_print("[OK] Query returned matching rows")


def visible_result_rows(driver: WebDriver, customer_name: str) -> list[WebElement]:
    rows = driver.find_elements(
        By.XPATH,
        (
            "//tr[.//*[contains(normalize-space(.), "
            f"{json.dumps(customer_name, ensure_ascii=False)}"
            ")]]"
        ),
    )
    return [row for row in rows if row.is_displayed()]


def select_first_result(driver: WebDriver, config: RunConfig) -> None:
    switch_to_lookup_dialog_frame(driver)
    if config.result_selection != "first":
        raise RuntimeError(f"Unsupported resultSelection: {config.result_selection}")

    rows = visible_result_rows(driver, config.customer_name)
    if not rows:
        raise RuntimeError(f"No visible lookup result contains {config.customer_name!r}.")

    first_row = rows[0]
    row_text = " ".join(first_row.text.split())
    safe_print("[STEP] Select first result:", row_text)
    ActionChains(driver).move_to_element(first_row).double_click(first_row).perform()

    switch_to_work_frame(driver)
    wait(driver, 20).until(lambda d: config.customer_name in d.find_element(By.TAG_NAME, "body").text)
    safe_print("[OK] Selected source result is present in the work-record form")


def select_lookup_result(
    driver: WebDriver,
    *,
    button_id: str,
    lookup_key: str,
    condition_text: str | None,
    result_contains: str | None = None,
) -> str:
    click_old_crm_button(driver, button_id)
    switch_to_lookup_dialog_frame(driver)
    wait(driver, 20).until(EC.presence_of_element_located((By.ID, "txtSEARCH")))
    if condition_text:
        set_lookup_condition_text(driver, condition_text)

    search_input = wait(driver, 10).until(EC.element_to_be_clickable((By.ID, "txtSEARCH")))
    search_input.clear()
    search_input.send_keys(lookup_key)
    driver.execute_script("okClick('btnSEARCH');")

    expected = result_contains or lookup_key
    wait(driver, 20).until(
        lambda d: expected in d.find_element(By.TAG_NAME, "body").text
        or len(visible_result_rows(d, expected)) > 0
    )
    rows = visible_result_rows(driver, expected)
    if not rows and expected != lookup_key:
        rows = visible_result_rows(driver, lookup_key)
    if not rows:
        raise RuntimeError(f"No visible lookup result contains {expected!r}.")

    first_row = rows[0]
    row_text = " ".join(first_row.text.split())
    safe_print("[STEP] Select lookup result:", row_text)
    ActionChains(driver).move_to_element(first_row).double_click(first_row).perform()
    switch_to_work_frame(driver)
    return row_text


def click_old_crm_button(driver: WebDriver, button_id: str) -> None:
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            switch_to_work_frame(driver)
            button = wait_enabled_old_crm_button(driver, button_id)
            driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", button)
            time.sleep(0.2)
            button.click()
            return
        except StaleElementReferenceException as exc:
            last_error = exc
            time.sleep(0.5)
    if last_error:
        raise last_error


def fill_source_lookup(driver: WebDriver, source_lookup_key: str) -> None:
    safe_print(f"[STEP] Fill 來源代號 from key: {source_lookup_key}")
    row_text = select_lookup_result(
        driver,
        button_id="FI024_btn",
        lookup_key=source_lookup_key,
        condition_text="客戶名稱",
        result_contains=source_lookup_key,
    )
    wait(driver, 20).until(lambda d: source_lookup_key in d.find_element(By.TAG_NAME, "body").text)
    safe_print("[OK] 來源代號 selected:", row_text)


def parse_work_nature_code(value: str) -> str:
    match = re.search(r"\d+", str(value or ""))
    if not match:
        raise RuntimeError(f"Could not parse work nature code from {value!r}")
    return match.group(0)


def parse_work_nature_name(value: str) -> str:
    text = str(value or "").strip()
    code = parse_work_nature_code(text)
    name = text.replace(code, "", 1).strip()
    return name or code


def fill_work_nature(driver: WebDriver, work_nature: str) -> None:
    if not work_nature:
        return
    code = parse_work_nature_code(work_nature)
    name = parse_work_nature_name(work_nature)
    safe_print(f"[STEP] Fill 工作性質代號: {code} / {name}")
    row_text = select_lookup_result(
        driver,
        button_id="FI017_btn",
        lookup_key=code,
        condition_text="工作性質代碼",
        result_contains=code,
    )
    wait(driver, 20).until(lambda d: code in d.find_element(By.ID, "FI017_txt").get_attribute("value"))
    safe_print("[OK] 工作性質代號 selected:", row_text)


def fill_record_content(driver: WebDriver, record_content: str) -> None:
    if not record_content:
        return
    safe_print("[STEP] Fill 紀錄內容")
    switch_to_work_frame(driver)
    textarea = wait(driver, 20).until(EC.presence_of_element_located((By.ID, "FI009_txt")))
    driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", textarea)
    textarea.clear()
    textarea.send_keys(record_content)
    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
        "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
        textarea,
    )
    safe_print("[OK] 紀錄內容 filled")


def fill_work_record(driver: WebDriver, record: WorkRecord) -> None:
    ensure_new_record(driver)
    fill_source_lookup(driver, record.source_lookup_key)
    fill_work_nature(driver, record.work_nature)
    fill_record_content(driver, record.record_content)


def accept_alerts_until_quiet(driver: WebDriver, *, seconds: float = 8.0) -> list[str]:
    messages: list[str] = []
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            alert = driver.switch_to.alert
            text = alert.text
            messages.append(text)
            safe_print("[ALERT]", text)
            alert.accept()
            time.sleep(0.5)
        except NoAlertPresentException:
            time.sleep(0.25)
    return messages


def save_current_record(driver: WebDriver, record: WorkRecord) -> None:
    label = f"sheet row {record.sheet_row}" if record.sheet_row else record.source_lookup_key
    safe_print(f"[STEP] Save record: {label}")
    click_old_crm_button(driver, "BtnSave")
    alert_messages = accept_alerts_until_quiet(driver)
    if any(is_blocking_save_alert(message) for message in alert_messages):
        raise RuntimeError(f"Save may have been blocked by CRM alert(s): {alert_messages}")
    time.sleep(2)
    ensure_new_record(driver)
    safe_print(f"[OK] Saved record and returned to input-ready form: {label}")


def is_blocking_save_alert(message: str) -> bool:
    text = str(message or "")
    blocking_markers = [
        "欄位未填值",
        "未填",
        "不可空白",
        "請輸入",
        "請選擇",
        "錯誤",
        "失敗",
    ]
    success_markers = ["成功", "完成"]
    return any(marker in text for marker in blocking_markers) and not any(
        marker in text for marker in success_markers
    )


def required_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(f"Missing required environment variable: {' or '.join(names)}")


def get_sheet_values(spreadsheet_id: str, range_name: str) -> list[list[str]]:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_service_account_file(
        required_env("SERVICE_ACCOUNT_FILE", "GOOGLE_APPLICATION_CREDENTIALS"),
        scopes=SCOPES,
    )
    service = build("sheets", "v4", credentials=credentials)
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueRenderOption="FORMATTED_VALUE",
    ).execute()
    return result.get("values", [])


def load_sheet_v_records(config: RunConfig) -> list[WorkRecord]:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path.cwd() / ".env")
    except Exception:
        pass

    spreadsheet_id = required_env("N1_SOURCE_SPREADSHEET_ID", "SPREADSHEET_ID")
    target_date = normalize_date_text(config.sheet_date)
    values = get_sheet_values(spreadsheet_id, f"'{config.sheet_tab}'!A:T")
    records: list[WorkRecord] = []

    def cell(row: list[str], index_1_based: int) -> str:
        return str(row[index_1_based - 1]).strip() if len(row) >= index_1_based else ""

    for row_number, row in enumerate(values, start=1):
        row_date = normalize_date_text(cell(row, 8))
        if row_date != target_date:
            continue
        source_lookup_key = cell(row, 15)
        work_nature = cell(row, 16)
        record_content = cell(row, 20)
        if not source_lookup_key:
            safe_print(f"[WARN] Skip sheet row {row_number}: column O is blank")
            continue
        records.append(
            WorkRecord(
                sheet_row=row_number,
                source_lookup_key=source_lookup_key,
                work_nature=work_nature,
                record_content=record_content,
            )
        )
        if config.max_rows > 0 and len(records) >= config.max_rows:
            break

    safe_print(
        f"[OK] Loaded {len(records)} sheet row(s) from {config.sheet_tab} "
        f"where H == {target_date}"
    )
    safe_print(json.dumps([record.__dict__ for record in records], ensure_ascii=False, indent=2))
    return records


def run(config: RunConfig) -> None:
    driver = build_driver(config)
    try:
        login(driver, config)
        open_work_record_maintenance(driver)
        ensure_new_record(driver)
        if getattr(config, "debug_controls", False):
            dump_visible_work_controls(driver)
            return
        if getattr(config, "debug_dialog", False):
            if getattr(config, "debug_dialog_after_source", False):
                fill_source_lookup(driver, config.customer_name)
            click_old_crm_button(driver, getattr(config, "debug_dialog_button", "FI024_btn"))
            dump_visible_dialog_controls(driver)
            return

        if not config.skip_test_record:
            test_record = WorkRecord(
                source_lookup_key=config.customer_name,
                work_nature=DEFAULT_TEST_WORK_NATURE,
            )
            fill_work_record(driver, test_record)
            save_current_record(driver, test_record)

        if config.from_sheet_v:
            records = load_sheet_v_records(config)
            for record in records:
                fill_work_record(driver, record)
                save_current_record(driver, record)

        safe_print("[DONE] Automation complete.")
        if config.keep_open:
            safe_print("[INFO] Browser left open because --keep-open was set.")
            return
    finally:
        if not config.keep_open:
            driver.quit()


def main() -> None:
    args = parse_args()
    config = load_config(args)
    object.__setattr__(config, "debug_controls", args.debug_controls)
    object.__setattr__(config, "debug_dialog", args.debug_dialog)
    object.__setattr__(config, "debug_dialog_button", args.debug_dialog_button)
    object.__setattr__(config, "debug_dialog_after_source", args.debug_dialog_after_source)
    try:
        run(config)
    except (TimeoutException, WebDriverException, RuntimeError) as exc:
        safe_print("[ERROR]", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
