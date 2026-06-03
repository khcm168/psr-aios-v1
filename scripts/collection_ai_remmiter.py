from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
from datetime import date
from email.message import EmailMessage
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env", override=True, encoding="utf-8-sig")

ARM_LOGIN_URL = os.getenv("ARM_LOGIN_URL", "http://192.168.0.187/BPMPlus/#/passport/login")
ARM_RECEIVABLE_URL = os.getenv("ARM_RECEIVABLE_URL", "http://192.168.0.187/BPMPlus/#/arm/armr01")

ARM_ACCOUNT = os.getenv("ARM_ACCOUNT", "108010")
ARM_PASSWORD = os.getenv("ARM_PASSWORD")
ARM_REMMITER_WEBAPP_URL = os.getenv("ARM_REMMITER_WEBAPP_URL") or os.getenv("ARM_WEBAPP_URL")
ARM_REMMITER_WEBAPP_ENV_VAR = "ARM_REMMITER_WEBAPP_URL" if os.getenv("ARM_REMMITER_WEBAPP_URL") else "ARM_WEBAPP_URL"
ARM_WEBAPP_TOKEN = os.getenv("ARM_WEBAPP_TOKEN")
ARM_BROWSER = os.getenv("ARM_BROWSER", "edge").strip().lower()

DOWNLOAD_DIR = Path(os.getenv("ARM_DOWNLOAD_DIR", r"C:\ARM_Downloads"))
DEBUG_DIR = Path(os.getenv("ARM_DEBUG_DIR", r"C:\ARM_Debug"))
GMAIL_TOKEN_FILE = Path(os.getenv("GMAIL_TOKEN_FILE", str(ROOT_DIR / "secrets" / "gmail-token.json")))
PAYMENT_INFO_DRAFT_TO = os.getenv("ARM_PAYMENT_INFO_DRAFT_TO", "khcm168@gmail.com")

ACTION_GET_QUEUE = "getAiRemmiterQueue"
ACTION_RECORD_RESULTS = "recordAiRemmiterResults"
CLOSING_NO_RE = re.compile(r"^61\d{2}-\d{10}$")
DOWNLOAD_SUFFIXES = {".xls", ".xlsx"}
PARTIAL_DOWNLOAD_SUFFIXES = {".crdownload", ".tmp"}
PAYMENT_INFO_EXPORT_TEXT = "\u6536\u6b3e\u8cc7\u8a0a\u532f\u51fa"
SEARCH_TEXT = "\u641c\u5c0b"
SHORT_PAUSE_SECONDS = 0.1
PAGE_SETTLE_SECONDS = 1.0
SEARCH_DIALOG_SETTLE_SECONDS = 0.3
SEARCH_RESULT_SETTLE_SECONDS = 0.8
ROW_ACTION_SETTLE_SECONDS = 0.3
CONFIRM_SETTLE_SECONDS = 0.6


def safe_print(*values: Any) -> None:
    text = " ".join(str(value) for value in values)
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace"))


def require_env(needs_browser: bool, needs_post: bool) -> None:
    missing = []
    if needs_browser and not ARM_PASSWORD:
        missing.append("ARM_PASSWORD")
    if needs_post and not ARM_REMMITER_WEBAPP_URL:
        missing.append("ARM_REMMITER_WEBAPP_URL or ARM_WEBAPP_URL")
    if needs_post and not ARM_WEBAPP_TOKEN:
        missing.append("ARM_WEBAPP_TOKEN")
    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))


def setup_driver():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    if ARM_BROWSER == "chrome":
        options = ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_experimental_option("prefs", download_preferences())
        return webdriver.Chrome(options=options)

    options = EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_experimental_option("prefs", download_preferences())
    return webdriver.Edge(options=options)


def download_preferences() -> dict[str, Any]:
    return {
        "download.default_directory": str(DOWNLOAD_DIR),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }


def save_debug(driver, name: str) -> None:
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_") or "debug"
    stamp = time.strftime("%Y%m%d_%H%M%S")
    html_path = DEBUG_DIR / f"{stamp}_{safe_name}.html"
    png_path = DEBUG_DIR / f"{stamp}_{safe_name}.png"
    html_path.write_text(driver.page_source, encoding="utf-8", errors="replace")
    driver.save_screenshot(str(png_path))
    safe_print("[DEBUG]", html_path, png_path)


def post_webapp(payload: dict[str, Any]) -> dict[str, Any]:
    request_payload = {"token": ARM_WEBAPP_TOKEN}
    request_payload.update(payload)
    response = requests.post(
        ARM_REMMITER_WEBAPP_URL,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=120,
    )
    try:
        result = response.json()
    except ValueError as exc:
        detail = (
            f"AI Remmiter WebApp returned HTTP {response.status_code} non-JSON from "
            f"{ARM_REMMITER_WEBAPP_ENV_VAR}. "
        )
        if response.status_code in {401, 403} and "<html" in response.text[:1000].lower():
            detail += (
                "Apps Script denied anonymous access before the remmiter JSON handler ran. "
                "Check the Web App deployment access is set to Everyone and that the /exec URL "
                "is from the Web App section, not the API executable URL."
            )
        elif response.status_code == 404 or "<html" in response.text[:1000].lower():
            detail += (
                "Check ARM_REMMITER_WEBAPP_URL points to a deployed Apps Script Web App "
                "/exec URL for the remmiter endpoint; the legacy ARM_WEBAPP_URL fallback "
                "may be missing, expired, or the wrong deployment type."
            )
        else:
            detail += response.text[:300]
        raise RuntimeError(detail) from exc
    if response.status_code != 200:
        raise RuntimeError(f"AI Remmiter WebApp returned HTTP {response.status_code}: {result}")
    if not result.get("ok"):
        message = "Apps Script error: " + str(result.get("error"))
        if ARM_REMMITER_WEBAPP_ENV_VAR == "ARM_WEBAPP_URL":
            message += " Set ARM_REMMITER_WEBAPP_URL to the dedicated AI Remmiter Web App URL."
        raise RuntimeError(message)
    return result

def fetch_queue() -> dict[str, Any]:
    safe_print("[STEP] Fetch AI Remmiter queue")
    response = post_webapp({"action": ACTION_GET_QUEUE})
    queue = response.get("result") or {}
    items = queue.get("items") or []
    invalid = queue.get("invalidCheckedRows") or []
    safe_print("[OK] Queue valid rows:", len(items), "invalid checked rows:", len(invalid))
    return queue


def post_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    safe_print("[STEP] Record AI Remmiter results")
    response = post_webapp({"action": ACTION_RECORD_RESULTS, "results": results})
    safe_print("[OK] Results recorded")
    return response.get("result") or {}


def build_collection_u_status(today: date | None = None) -> str:
    day = today or date.today()
    return day.strftime("%m/%d") + "\u958b\u59cb\u90f5\u5c40\u532f\u6b3e\u4f5c\u696d"


def mark_step_collection_u_status(result: dict[str, Any], today: date | None = None) -> None:
    status_text = build_collection_u_status(today)
    result["message"] = status_text
    result["collectionUText"] = status_text
    result["statusText"] = status_text
    result["collectionUValue"] = status_text


def build_single_step_post_result(item: dict[str, Any], step_result: dict[str, Any]) -> dict[str, Any]:
    row_number = step_result.get("rowNumber")
    closing_no = step_result.get("closingNo")
    return {
        "groupType": item.get("groupType"),
        "invoiceNo": item.get("invoiceNo"),
        "rowNumbers": [row_number] if row_number is not None else [],
        "closingNumbers": [closing_no] if closing_no else [],
        "ok": bool(step_result.get("ok")),
        "message": step_result.get("message") or "",
        "collectionUText": step_result.get("collectionUText") or step_result.get("message") or "",
        "statusText": step_result.get("statusText") or step_result.get("message") or "",
        "collectionUValue": step_result.get("collectionUValue") or step_result.get("message") or "",
        "steps": [step_result],
    }


def wait_document_ready(driver, timeout_seconds: int = 30) -> None:
    WebDriverWait(driver, timeout_seconds).until(
        lambda current_driver: current_driver.execute_script("return document.readyState") == "complete"
    )


def visible_enabled(elements):
    for element in elements:
        try:
            if element.is_displayed() and element.is_enabled():
                return element
        except Exception:
            continue
    return None


def set_input_value(driver, element, value: str) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(SHORT_PAUSE_SECONDS)

    try:
        element.click()
        element.clear()
        element.send_keys(value)
        return
    except Exception:
        pass

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


def wait_for_editable_input(driver, wait: WebDriverWait, xpaths: list[str], label: str):
    def find_input(current_driver):
        for xpath in xpaths:
            for element in current_driver.find_elements(By.XPATH, xpath):
                try:
                    if not element.is_displayed() or not element.is_enabled():
                        continue
                    if element.get_attribute("readonly") or element.get_attribute("disabled"):
                        continue
                    return element
                except Exception:
                    continue
        return False

    return wait.until(find_input, message=f"Could not find editable {label} input")


def wait_for_labeled_input(driver, wait: WebDriverWait, label_text: str, allow_readonly: bool = False):
    def find_labeled_input(current_driver):
        script = """
        const wanted = arguments[0].replace(/[:：]\\s*$/, '');
        const allowReadonly = arguments[1];
        const isVisible = (el) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            rect.width > 0 &&
            rect.height > 0;
        };
        const labels = Array.from(document.querySelectorAll('label, span, div, td, th'))
          .filter((el) => isVisible(el))
          .filter((el) => el.children.length === 0 || el.querySelectorAll('input, textarea, select').length === 0)
          .filter((el) => el.textContent.trim().replace(/[:：]\\s*$/, '') === wanted);

        for (const label of labels) {
          const labelRect = label.getBoundingClientRect();
          const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]), textarea'))
            .filter((el) => isVisible(el))
            .filter((el) => !el.disabled && (allowReadonly || !el.readOnly))
            .map((el) => ({ el, rect: el.getBoundingClientRect() }))
            .filter((item) => item.rect.left >= labelRect.right - 5)
            .filter((item) => Math.abs((item.rect.top + item.rect.height / 2) - (labelRect.top + labelRect.height / 2)) < 24)
            .sort((a, b) => a.rect.left - b.rect.left);
          if (inputs.length) return inputs[0].el;
        }
        return null;
        """
        element = current_driver.execute_script(script, label_text, allow_readonly)
        if not element:
            return False
        try:
            if not allow_readonly and element.get_attribute("readonly"):
                return False
            current_value = str(element.get_attribute("value") or "").strip()
            if current_value and current_value.upper() == "TOP":
                return False
            return element
        except Exception:
            return False

    return wait.until(find_labeled_input, message=f"Could not find editable {label_text} input")


def click_first(driver, wait: WebDriverWait, xpaths: list[str], label: str):
    def find_clickable(current_driver):
        for xpath in xpaths:
            element = visible_enabled(current_driver.find_elements(By.XPATH, xpath))
            if element is not None:
                return element
        return False

    element = wait.until(find_clickable, message=f"Could not find clickable {label}")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(SHORT_PAUSE_SECONDS)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    return element


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return "'" + value + "'"
    if '"' not in value:
        return '"' + value + '"'
    return "concat(" + ", \"'\", ".join("'" + part + "'" for part in value.split("'")) + ")"


def login_arm(driver, wait: WebDriverWait) -> None:
    safe_print("[STEP] Login ARM")
    driver.get(ARM_LOGIN_URL)
    wait_document_ready(driver)
    time.sleep(0.5)
    save_debug(driver, "ai_remmiter_login_page")

    account_input = wait_for_editable_input(
        driver,
        wait,
        [
            "//input[@formcontrolname='userName']",
            "//input[contains(@placeholder, '\u5e33\u865f') or contains(@aria-label, '\u5e33\u865f')]",
            "//input[(not(@type) or @type='text' or @type='email' or @type='tel') and not(@readonly) and not(@disabled)]",
        ],
        "account",
    )
    password_input = wait_for_editable_input(
        driver,
        wait,
        [
            "//input[@formcontrolname='password']",
            "//input[@type='password']",
            "//input[contains(@placeholder, '\u5bc6\u78bc') or contains(@aria-label, '\u5bc6\u78bc')]",
        ],
        "password",
    )

    set_input_value(driver, account_input, ARM_ACCOUNT)
    set_input_value(driver, password_input, ARM_PASSWORD or "")
    click_first(
        driver,
        wait,
        [
            "//button[contains(normalize-space(.), '\u767b\u5165') or contains(normalize-space(.), 'Login')]",
            "//span[contains(normalize-space(.), '\u767b\u5165') or contains(normalize-space(.), 'Login')]/ancestor::button[1]",
            "//button[@type='submit']",
        ],
        "login button",
    )
    time.sleep(PAGE_SETTLE_SECONDS)
    save_debug(driver, "ai_remmiter_after_login")
    safe_print("[OK] Login submitted")


def open_arm_receivables(driver, wait: WebDriverWait) -> None:
    safe_print("[STEP] Open ARM receivables page")
    driver.get(ARM_RECEIVABLE_URL)
    wait_document_ready(driver)
    time.sleep(0.5)
    save_debug(driver, "ai_remmiter_armr01")

    detail_xpath = (
        "//span[contains(@class, 'ng-star-inserted') and "
        "(contains(normalize-space(.), '\u9ede\u6211\u89c0\u770b\u660e\u7d30') or contains(normalize-space(.), '\u89c0\u770b\u660e\u7d30'))]"
    )

    try:
        WebDriverWait(driver, 5, poll_frequency=0.2).until(EC.presence_of_element_located((By.XPATH, detail_xpath)))
    except TimeoutException:
        safe_print("[STEP] Direct route stayed on home; click ARM receivables menu")
        click_first(
            driver,
            wait,
            [
                "//a[@data-id='3' or .//span[@title='\u903e\u671f\u61c9\u6536\u5e33\u6b3e'] or .//span[normalize-space(.)='\u903e\u671f\u61c9\u6536\u5e33\u6b3e']]",
                "//a[.//*[contains(normalize-space(.), '\u61c9\u6536') and contains(normalize-space(.), '\u5e33\u6b3e')]]",
                "//*[@role='menuitem' and contains(normalize-space(.), '\u61c9\u6536')]",
            ],
            "ARM receivables menu",
        )
        time.sleep(PAGE_SETTLE_SECONDS)
        save_debug(driver, "ai_remmiter_after_click_receivables_menu")

    safe_print("[STEP] Click \u9ede\u6211\u89c0\u770b\u660e\u7d30")
    click_first(driver, wait, [detail_xpath], "\u9ede\u6211\u89c0\u770b\u660e\u7d30")
    time.sleep(PAGE_SETTLE_SECONDS)
    save_debug(driver, "ai_remmiter_after_click_detail")
    safe_print("[OK] Detail clicked")


def click_search(driver, wait: WebDriverWait) -> None:
    click_first(
        driver,
        wait,
        [
            "//button[contains(normalize-space(.), '\u641c\u5c0b')]",
            "//span[contains(normalize-space(.), '\u641c\u5c0b')]/ancestor::button[1]",
            "//*[@role='button' and contains(normalize-space(.), '\u641c\u5c0b')]",
            "//*[contains(@class, 'btn') and contains(normalize-space(.), '\u641c\u5c0b')]",
        ],
        "search button",
    )


def clear_download_folder(download_dir: Path = DOWNLOAD_DIR) -> None:
    download_dir.mkdir(parents=True, exist_ok=True)
    for file_path in download_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in DOWNLOAD_SUFFIXES | PARTIAL_DOWNLOAD_SUFFIXES:
            file_path.unlink()


def latest_completed_download(download_dir: Path = DOWNLOAD_DIR) -> Path | None:
    if not download_dir.exists():
        return None
    downloads = sorted(
        [
            file_path
            for file_path in download_dir.iterdir()
            if file_path.is_file() and file_path.suffix.lower() in DOWNLOAD_SUFFIXES
        ],
        key=lambda file_path: file_path.stat().st_mtime,
        reverse=True,
    )
    return downloads[0] if downloads else None


def has_partial_downloads(download_dir: Path = DOWNLOAD_DIR) -> bool:
    if not download_dir.exists():
        return False
    return any(
        file_path.is_file() and file_path.suffix.lower() in PARTIAL_DOWNLOAD_SUFFIXES
        for file_path in download_dir.iterdir()
    )


def wait_for_download(download_dir: Path = DOWNLOAD_DIR, timeout_seconds: int = 120) -> Path:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        latest_download = latest_completed_download(download_dir)
        if latest_download is not None and not has_partial_downloads(download_dir):
            safe_print("[OK] Downloaded:", latest_download)
            return latest_download
        time.sleep(0.5)
    raise TimeoutError(f"Excel download did not finish within {timeout_seconds} seconds.")


def choose_button_three_left(toolbar_buttons: list[Any], search_button: Any) -> Any:
    try:
        search_index = next(
            index
            for index, button in enumerate(toolbar_buttons)
            if button is search_button or button == search_button
        )
    except StopIteration as exc:
        raise RuntimeError("Search button was not found in the visible toolbar button list.") from exc

    export_index = search_index - 3
    if export_index < 0:
        raise RuntimeError("Could not find the toolbar button three positions left of search.")
    return toolbar_buttons[export_index]


def find_search_button(driver, wait: WebDriverWait):
    def find_clickable_search(current_driver):
        for xpath in [
            f"//button[contains(normalize-space(.), '{SEARCH_TEXT}')]",
            f"//span[contains(normalize-space(.), '{SEARCH_TEXT}')]/ancestor::button[1]",
            f"//*[@role='button' and contains(normalize-space(.), '{SEARCH_TEXT}')]",
            f"//*[contains(@class, 'btn') and contains(normalize-space(.), '{SEARCH_TEXT}')]",
        ]:
            element = visible_enabled(current_driver.find_elements(By.XPATH, xpath))
            if element is not None:
                return element
        return False

    return wait.until(find_clickable_search, message="Could not find clickable search button")


def visible_toolbar_buttons_near(driver, anchor_button) -> list[Any]:
    anchor_rect = anchor_button.rect or {}
    anchor_center_y = float(anchor_rect.get("y", 0)) + float(anchor_rect.get("height", 0)) / 2
    y_tolerance = max(24.0, float(anchor_rect.get("height", 0)) * 0.8)
    candidates = []
    seen = set()

    for element in driver.find_elements(By.XPATH, "//button | //*[@role='button'] | //a"):
        try:
            if not element.is_displayed() or not element.is_enabled():
                continue
            element_id = getattr(element, "id", None)
            if element_id and element_id in seen:
                continue
            rect = element.rect or {}
            width = float(rect.get("width", 0))
            height = float(rect.get("height", 0))
            if width <= 0 or height <= 0:
                continue
            center_y = float(rect.get("y", 0)) + height / 2
            if abs(center_y - anchor_center_y) > y_tolerance:
                continue
            candidates.append((float(rect.get("x", 0)), element))
            if element_id:
                seen.add(element_id)
        except StaleElementReferenceException:
            return visible_toolbar_buttons_near(driver, anchor_button)
        except Exception:
            continue

    candidates.sort(key=lambda item: item[0])
    return [element for _, element in candidates]


def click_payment_info_export(driver, wait: WebDriverWait) -> None:
    safe_print("[STEP] Click", PAYMENT_INFO_EXPORT_TEXT)
    clear_download_folder()
    search_button = find_search_button(driver, wait)
    toolbar_buttons = visible_toolbar_buttons_near(driver, search_button)
    export_button = choose_button_three_left(toolbar_buttons, search_button)
    export_text = " ".join(str(export_button.text or "").split())
    if export_text and PAYMENT_INFO_EXPORT_TEXT not in export_text:
        raise RuntimeError(
            f"Expected toolbar button three positions left of search to contain "
            f"{PAYMENT_INFO_EXPORT_TEXT!r}; got {export_text!r}."
        )

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", export_button)
    time.sleep(SHORT_PAUSE_SECONDS)
    try:
        export_button.click()
    except Exception:
        driver.execute_script("arguments[0].click();", export_button)
    safe_print("[OK]", PAYMENT_INFO_EXPORT_TEXT, "clicked")


def wait_for_payment_info_export_dialog(driver, wait: WebDriverWait):
    def find_date_dialog(current_driver):
        for dialog in reversed(find_visible_dialogs(current_driver)):
            try:
                if not dialog.is_displayed():
                    continue
                visible_date_fields = []
                for field in dialog.find_elements(
                    By.XPATH,
                    ".//input[not(@type='hidden') and not(@disabled)]"
                    " | .//textarea[not(@disabled)]"
                    " | .//*[contains(normalize-space(.), '\u65e5\u671f')]",
                ):
                    try:
                        if field.is_displayed():
                            visible_date_fields.append(field)
                    except Exception:
                        continue
                if visible_date_fields:
                    return dialog
            except Exception:
                continue
        return False

    return wait.until(find_date_dialog, message="Payment info export date dialog did not appear")


def confirm_payment_info_export_dialog(driver, wait: WebDriverWait) -> None:
    wait_for_payment_info_export_dialog(driver, wait)
    click_dialog_ok(driver, wait, "payment info export date dialog")
    safe_print("[OK] Payment info export date dialog confirmed")


def build_payment_info_export_message(downloaded_path: Path, to_address: str, exported_on: date | None = None) -> EmailMessage:
    export_day = exported_on or date.today()
    message = EmailMessage()
    message["To"] = to_address
    message["Subject"] = f"ARM 收款資訊匯出 {export_day.strftime('%Y/%m/%d')}"
    message.set_content(
        "\n".join(
            [
                "Attached is the ARM 收款資訊匯出 file.",
                "",
                f"Export date: {export_day.strftime('%Y/%m/%d')}",
                f"Local file: {downloaded_path}",
            ]
        )
    )

    content_type, _ = mimetypes.guess_type(str(downloaded_path))
    if content_type:
        maintype, subtype = content_type.split("/", 1)
    else:
        maintype, subtype = "application", "octet-stream"
    message.add_attachment(
        downloaded_path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=downloaded_path.name,
    )
    return message


def encode_gmail_raw_message(message: EmailMessage) -> str:
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")


def create_gmail_draft_with_attachment(downloaded_path: Path, to_address: str = PAYMENT_INFO_DRAFT_TO) -> dict[str, Any]:
    token_file = GMAIL_TOKEN_FILE.expanduser()
    if not token_file.is_absolute():
        token_file = ROOT_DIR / token_file

    if not token_file.exists():
        raise RuntimeError(
            "Missing Gmail OAuth token file: "
            + str(token_file)
            + ". Set GMAIL_TOKEN_FILE to a Gmail user OAuth token JSON with gmail.compose scope."
        )

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials.from_authorized_user_file(
        str(token_file),
        scopes=["https://www.googleapis.com/auth/gmail.compose"],
    )
    service = build("gmail", "v1", credentials=credentials)
    message = build_payment_info_export_message(downloaded_path, to_address)
    draft = (
        service.users()
        .drafts()
        .create(userId="me", body={"message": {"raw": encode_gmail_raw_message(message)}})
        .execute()
    )
    safe_print("[OK] Gmail draft created:", draft.get("id"), "to", to_address)
    return draft


def dry_test_payment_info_export(create_draft: bool = False, draft_to: str = PAYMENT_INFO_DRAFT_TO) -> Path:
    driver = setup_driver()
    wait = WebDriverWait(driver, 20, poll_frequency=0.2)
    try:
        login_arm(driver, wait)
        open_arm_receivables(driver, wait)
        save_debug(driver, "payment_info_export_before_click")
        click_payment_info_export(driver, wait)
        time.sleep(PAGE_SETTLE_SECONDS)
        save_debug(driver, "payment_info_export_dialog")
        confirm_payment_info_export_dialog(driver, wait)
        downloaded_path = wait_for_download()
        save_debug(driver, "payment_info_export_download_confirmed")
        safe_print("[OK] Downloaded payment info export:", downloaded_path)
        if create_draft:
            create_gmail_draft_with_attachment(downloaded_path, draft_to)
        return downloaded_path
    finally:
        driver.quit()


def fill_closing_no(driver, wait: WebDriverWait, closing_no: str) -> None:
    try:
        input_element = wait_for_labeled_input(driver, wait, "\u7d50\u5e33\u55ae\u865f")
    except TimeoutException:
        input_element = wait_for_editable_input(
            driver,
            wait,
            [
                "//label[normalize-space(.)='\u7d50\u5e33\u55ae\u865f' or normalize-space(.)='\u7d50\u5e33\u55ae\u865f\uff1a' or normalize-space(.)='\u7d50\u5e33\u55ae\u865f:']/following::input[not(@type='hidden')][1]",
                "//*[self::span or self::div or self::td][normalize-space(.)='\u7d50\u5e33\u55ae\u865f' or normalize-space(.)='\u7d50\u5e33\u55ae\u865f\uff1a' or normalize-space(.)='\u7d50\u5e33\u55ae\u865f:']/following::input[not(@type='hidden')][1]",
                "//input[contains(@placeholder, '\u7d50\u5e33\u55ae\u865f') or contains(@aria-label, '\u7d50\u5e33\u55ae\u865f') or contains(@title, '\u7d50\u5e33\u55ae\u865f')]",
            ],
            "closing number",
        )

    current_value = str(input_element.get_attribute("value") or "").strip()
    if current_value.upper() == "TOP":
        raise RuntimeError("Refusing to fill 公司別 input; 結帳單號 field was not located.")
    set_input_value(driver, input_element, closing_no)


def normalize_amount(value: Any) -> str:
    text = str(value or "").replace(",", "").strip()
    if not text:
        raise RuntimeError("Missing unpaid amount.")
    try:
        number = float(text)
    except ValueError as exc:
        raise RuntimeError(f"Invalid unpaid amount: {value}") from exc
    if number <= 0:
        raise RuntimeError(f"Unpaid amount must be positive: {value}")
    if number.is_integer():
        return str(int(number))
    return str(number)


def fill_original_currency_amount(driver, wait: WebDriverWait, amount: str) -> None:
    input_element = wait_for_labeled_input(driver, wait, "\u539f\u5e63\u6536\u6b3e\u91d1\u984d")
    set_input_value(driver, input_element, amount)


def wait_for_text(driver, wait: WebDriverWait, text: str) -> None:
    xpath = "//*[contains(normalize-space(.), '" + text + "')]"
    wait.until(EC.presence_of_element_located((By.XPATH, xpath)), message=f"Could not find text: {text}")


def click_ok(driver, wait: WebDriverWait) -> None:
    click_first(
        driver,
        wait,
        [
            "//button[normalize-space(.)='OK' or contains(normalize-space(.), '\u78ba\u5b9a')]",
            "//span[normalize-space(.)='OK' or contains(normalize-space(.), '\u78ba\u5b9a')]/ancestor::button[1]",
            "//*[@role='button' and (normalize-space(.)='OK' or contains(normalize-space(.), '\u78ba\u5b9a'))]",
        ],
        "OK button",
    )


def find_visible_dialogs(driver) -> list[Any]:
    dialogs = []
    for xpath in [
        "//*[contains(@class, 'ant-modal') and not(contains(@style, 'display: none'))]",
        "//*[contains(@class, 'modal') or contains(@class, 'dialog') or contains(@class, 'cdk-overlay-pane') or @role='dialog']",
    ]:
        for dialog in driver.find_elements(By.XPATH, xpath):
            try:
                if dialog.is_displayed() and dialog not in dialogs:
                    dialogs.append(dialog)
            except Exception:
                continue
    return dialogs


def click_dialog_ok(driver, wait: WebDriverWait, label: str):
    def find_button(current_driver):
        for dialog in reversed(find_visible_dialogs(current_driver)):
            buttons = dialog.find_elements(
                By.XPATH,
                ".//button[normalize-space(.)='OK' or contains(normalize-space(.), '\u78ba\u5b9a')]"
                " | .//span[normalize-space(.)='OK' or contains(normalize-space(.), '\u78ba\u5b9a')]/ancestor::button[1]",
            )
            button = visible_enabled(buttons)
            if button is not None:
                return button
        return False

    element = wait.until(find_button, message=f"Could not find {label} OK button")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(SHORT_PAUSE_SECONDS)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    return element


def click_confirmation_only_dialog_ok(driver, wait: WebDriverWait):
    def find_button(current_driver):
        for dialog in reversed(find_visible_dialogs(current_driver)):
            editable_fields = dialog.find_elements(
                By.XPATH,
                ".//input[not(@type='hidden') and not(@disabled) and not(@readonly)]"
                " | .//textarea[not(@disabled) and not(@readonly)]"
                " | .//select[not(@disabled)]",
            )
            visible_editable_fields = []
            for field in editable_fields:
                try:
                    if field.is_displayed():
                        visible_editable_fields.append(field)
                except Exception:
                    continue
            if visible_editable_fields:
                continue

            buttons = dialog.find_elements(
                By.XPATH,
                ".//button[normalize-space(.)='OK' or contains(normalize-space(.), '\u78ba\u5b9a')]"
                " | .//span[normalize-space(.)='OK' or contains(normalize-space(.), '\u78ba\u5b9a')]/ancestor::button[1]",
            )
            button = visible_enabled(buttons)
            if button is not None:
                return button
        return False

    element = wait.until(find_button, message="Could not find confirmation-only OK button")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(SHORT_PAUSE_SECONDS)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    return element


def wait_for_dialogs_to_close(driver) -> None:
    try:
        WebDriverWait(driver, 5, poll_frequency=0.2).until(lambda current_driver: not find_visible_dialogs(current_driver))
    except TimeoutException:
        pass


def click_followup_confirm(driver, item: dict[str, Any], step_name: str, closing_no: str) -> None:
    time.sleep(0.2)

    try:
        alert = WebDriverWait(driver, 1, poll_frequency=0.2).until(EC.alert_is_present())
        save_debug(driver, debug_name(item, step_name + "_confirm_alert", closing_no))
        alert.accept()
        time.sleep(CONFIRM_SETTLE_SECONDS)
        wait_for_dialogs_to_close(driver)
        return
    except TimeoutException:
        pass

    click_confirmation_only_dialog_ok(driver, WebDriverWait(driver, 6, poll_frequency=0.2))
    save_debug(driver, debug_name(item, step_name + "_confirm_ok_clicked", closing_no))
    time.sleep(CONFIRM_SETTLE_SECONDS)
    wait_for_dialogs_to_close(driver)


def find_result_row(driver, wait: WebDriverWait, closing_no: str):
    closing_literal = xpath_literal(closing_no)

    def find_row(current_driver):
        rows = current_driver.find_elements(
            By.XPATH,
            "//tr[.//*[normalize-space(.)="
            + closing_literal
            + " or contains(normalize-space(.), "
            + closing_literal
            + ")]]",
        )
        return visible_enabled(rows) or False

    return wait.until(find_row, message=f"Could not find result row for closing number {closing_no}")


def click_row_textless_action(driver, wait: WebDriverWait, closing_no: str):
    def find_action(current_driver):
        row = find_result_row(current_driver, wait, closing_no)
        buttons = row.find_elements(
            By.XPATH,
            ".//button[not(contains(normalize-space(.), '\u6536\u6b3e')) "
            "and not(contains(normalize-space(.), '\u627f\u8afe')) "
            "and not(contains(normalize-space(.), 'OK')) "
            "and not(contains(normalize-space(.), '\u78ba\u5b9a')) "
            "and (not(normalize-space(.)) or @nz-row-expand-button or contains(@class, 'ng-star-inserted'))]",
        )
        candidates = []
        for button in buttons:
            try:
                if not button.is_displayed() or not button.is_enabled():
                    continue
                rect = button.rect or {}
                candidates.append((float(rect.get("x", 0)), button))
            except StaleElementReferenceException:
                return False
            except Exception:
                continue
        if not candidates:
            return False
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    element = wait.until(find_action, message=f"Could not find textless row action for {closing_no}")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(SHORT_PAUSE_SECONDS)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    time.sleep(ROW_ACTION_SETTLE_SECONDS)
    return element


def click_row_payment_collection(driver, wait: WebDriverWait, closing_no: str):
    def find_payment_button(current_driver):
        row = find_result_row(current_driver, wait, closing_no)
        buttons = row.find_elements(
            By.XPATH,
            ".//button[contains(normalize-space(.), '\u6536\u6b3e') "
            "and (contains(normalize-space(.), '+') or .//*[contains(normalize-space(.), '+')])]"
            " | .//span[contains(normalize-space(.), '\u6536\u6b3e')]/ancestor::button[1]"
            " | .//*[@role='button' and contains(normalize-space(.), '\u6536\u6b3e')]",
        )
        return visible_enabled(buttons) or False

    element = wait.until(find_payment_button, message=f"Could not find row + \u6536\u6b3e button for {closing_no}")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(SHORT_PAUSE_SECONDS)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    return element


def click_payment_collection(driver, wait: WebDriverWait, closing_no: str, item: dict[str, Any], step_name: str) -> None:
    find_result_row(driver, wait, closing_no)
    save_debug(driver, debug_name(item, step_name + "_row_found", closing_no))
    click_row_textless_action(driver, wait, closing_no)
    save_debug(driver, debug_name(item, step_name + "_row_action_clicked", closing_no))
    find_result_row(driver, wait, closing_no)
    click_row_payment_collection(driver, wait, closing_no)
    save_debug(driver, debug_name(item, step_name + "_payment_clicked", closing_no))


def wait_for_payment_popup(driver, wait: WebDriverWait) -> None:
    def popup_with_blank_inputs(current_driver):
        candidates = []
        candidates.extend(
            current_driver.find_elements(
                By.XPATH,
                "//*[contains(@class, 'modal') or contains(@class, 'dialog') or contains(@class, 'cdk-overlay-pane') or @role='dialog']",
            )
        )
        candidates.extend(
            current_driver.find_elements(
                By.XPATH,
                "//*[contains(normalize-space(.), '\u6536\u6b3e') and (.//input or .//textarea)]",
            )
        )

        for candidate in candidates:
            try:
                if not candidate.is_displayed():
                    continue
                blank_inputs = candidate.find_elements(
                    By.XPATH,
                    ".//input[not(@type='hidden') and not(@disabled) and not(@readonly) and not(string-length(@value) > 0)]"
                    " | .//textarea[not(@disabled) and not(@readonly) and not(string-length(.) > 0)]",
                )
                if blank_inputs:
                    return candidate
            except Exception:
                continue
        return False

    wait.until(popup_with_blank_inputs, message="Payment popup with blank editable fields did not appear")


def search_closing_no(driver, wait: WebDriverWait, closing_no: str) -> None:
    click_search(driver, wait)
    time.sleep(SEARCH_DIALOG_SETTLE_SECONDS)
    fill_closing_no(driver, wait, closing_no)
    click_ok(driver, wait)
    time.sleep(SEARCH_RESULT_SETTLE_SECONDS)


def click_today_link(driver, wait: WebDriverWait) -> None:
    click_first(
        driver,
        wait,
        [
            "//a[normalize-space(.)='\u4eca\u5929']",
            "//span[normalize-space(.)='\u4eca\u5929']/ancestor::*[self::a or self::button][1]",
            "//*[contains(@class, 'today') and contains(normalize-space(.), '\u4eca\u5929')]",
        ],
        "\u4eca\u5929 link",
    )


def set_discount_return_today(driver, wait: WebDriverWait) -> None:
    wait_for_text(driver, wait, "\u6298\u8b93\u7c3d\u56de\u65e5")
    date_input = wait_for_labeled_input(driver, wait, "\u6298\u8b93\u7c3d\u56de\u65e5", allow_readonly=True)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", date_input)
    try:
        date_input.click()
    except Exception:
        driver.execute_script("arguments[0].click();", date_input)
    time.sleep(0.2)
    click_today_link(driver, wait)
    time.sleep(0.2)


def run_cash_step(driver, wait: WebDriverWait, item: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    closing_no = str(step.get("closingNo") or "").strip()
    amount = normalize_amount(item.get("cashAmountText") or item.get("cashAmount"))
    result = {
        "stepType": "cash",
        "rowNumber": step.get("rowNumber"),
        "closingNo": closing_no,
        "ok": False,
        "message": "",
    }

    if not CLOSING_NO_RE.match(closing_no):
        result["message"] = "Invalid cash closing number."
        return result

    safe_print("[STEP] Cash", closing_no, "invoice", item.get("invoiceNo"), "amount", amount)
    search_closing_no(driver, wait, closing_no)
    click_payment_collection(driver, wait, closing_no, item, "cash")
    wait_for_payment_popup(driver, wait)
    save_debug(driver, debug_name(item, "cash_popup_opened", closing_no))
    fill_original_currency_amount(driver, wait, amount)
    save_debug(driver, debug_name(item, "cash_filled", closing_no))
    click_dialog_ok(driver, wait, "cash data popup")
    save_debug(driver, debug_name(item, "cash_data_ok_clicked", closing_no))
    click_followup_confirm(driver, item, "cash", closing_no)
    result["ok"] = True
    mark_step_collection_u_status(result)
    return result


def run_cod_step(driver, wait: WebDriverWait, item: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    closing_no = str(step.get("closingNo") or "").strip()
    result = {
        "stepType": "cod",
        "rowNumber": step.get("rowNumber"),
        "closingNo": closing_no,
        "ok": False,
        "message": "",
    }

    if not CLOSING_NO_RE.match(closing_no):
        result["message"] = "Invalid COD closing number."
        return result

    safe_print("[STEP] COD", closing_no, "invoice", item.get("invoiceNo"))
    search_closing_no(driver, wait, closing_no)
    click_payment_collection(driver, wait, closing_no, item, "cod")
    wait_for_text(driver, wait, "\u6298\u8b93")
    save_debug(driver, debug_name(item, "cod_popup_opened", closing_no))
    set_discount_return_today(driver, wait)
    save_debug(driver, debug_name(item, "cod_today", closing_no))
    click_dialog_ok(driver, wait, "COD data popup")
    save_debug(driver, debug_name(item, "cod_data_ok_clicked", closing_no))
    click_followup_confirm(driver, item, "cod", closing_no)
    result["ok"] = True
    mark_step_collection_u_status(result)
    return result


def debug_name(item: dict[str, Any], step_name: str, closing_no: str) -> str:
    return "_".join(
        [
            "ai_remmiter",
            str(item.get("groupType") or "group"),
            str(item.get("invoiceNo") or "no_invoice"),
            step_name,
            closing_no,
        ]
    )


def run_group(driver, wait: WebDriverWait, item: dict[str, Any], on_step_success=None) -> dict[str, Any]:
    row_numbers = list(item.get("rowNumbers") or [])
    closing_numbers = list(item.get("closingNumbers") or [])
    result = {
        "groupType": item.get("groupType"),
        "invoiceNo": item.get("invoiceNo"),
        "rowNumbers": row_numbers,
        "closingNumbers": closing_numbers,
        "ok": False,
        "message": "",
        "steps": [],
    }

    try:
        if item.get("cashStep"):
            cash_result = run_cash_step(driver, wait, item, item["cashStep"])
            result["steps"].append(cash_result)
            if not cash_result.get("ok"):
                result["message"] = cash_result.get("message") or "Cash step failed."
                return result
            if on_step_success:
                on_step_success(build_single_step_post_result(item, cash_result))

        if item.get("codStep"):
            cod_result = run_cod_step(driver, wait, item, item["codStep"])
            result["steps"].append(cod_result)
            if not cod_result.get("ok"):
                result["message"] = cod_result.get("message") or "COD step failed."
                return result
            if on_step_success:
                on_step_success(build_single_step_post_result(item, cod_result))

        result["ok"] = True
        result["message"] = "Group submitted."
        safe_print("[OK]", item.get("groupType"), item.get("invoiceNo"))
    except Exception as err:
        result["message"] = str(err)
        closing_hint = "_".join(closing_numbers) if closing_numbers else str(item.get("invoiceNo") or "unknown")
        save_debug(driver, debug_name(item, "failed", closing_hint))
        safe_print("[ERROR]", item.get("groupType"), item.get("invoiceNo"), err)

    return result


def select_items(queue: dict[str, Any], limit: int | None) -> list[dict[str, Any]]:
    items = list(queue.get("items") or [])
    if limit is not None:
        items = items[: max(limit, 0)]
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ARM AI Remmiter searches from checked Collection!U groups.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print the queue without opening ARM.")
    parser.add_argument(
        "--dry-test-payment-info-export",
        action="store_true",
        help="Open ARM, click the payment info export toolbar button, confirm the default date, and report the download.",
    )
    parser.add_argument(
        "--draft-payment-info-export-email",
        action="store_true",
        help="After --dry-test-payment-info-export downloads the Excel file, create a Gmail draft with the file attached.",
    )
    parser.add_argument(
        "--draft-to",
        default=PAYMENT_INFO_DRAFT_TO,
        help=f"Gmail draft recipient for the payment info export attachment. Default: {PAYMENT_INFO_DRAFT_TO}",
    )
    parser.add_argument("--limit", type=int, help="Process only the first N checked groups.")
    parser.add_argument("--skip-post-results", action="store_true", help="Do not write final TRUE/FALSE results back to Collection!U.")
    args = parser.parse_args()

    if args.dry_test_payment_info_export:
        require_env(needs_browser=True, needs_post=False)
        dry_test_payment_info_export(
            create_draft=args.draft_payment_info_export_email,
            draft_to=args.draft_to,
        )
        return

    require_env(needs_browser=not args.dry_run, needs_post=True)
    queue = fetch_queue()
    items = select_items(queue, args.limit)

    if args.dry_run:
        safe_print(
            json.dumps(
                {
                    "ok": True,
                    "dryRun": True,
                    "selectedRows": len(items),
                    "items": items,
                    "invalidCheckedRows": queue.get("invalidCheckedRows") or [],
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return

    if not items:
        safe_print("[DONE] No checked AI Remmiter rows to process.")
        return

    driver = setup_driver()
    wait = WebDriverWait(driver, 20, poll_frequency=0.2)
    try:
        login_arm(driver, wait)
        open_arm_receivables(driver, wait)
        results = []

        def post_step_result(step_post_result: dict[str, Any]) -> None:
            if args.skip_post_results:
                return
            post_result = post_results([step_post_result])
            safe_print(json.dumps(post_result, ensure_ascii=True, indent=2))

        for item in items:
            result = run_group(driver, wait, item, on_step_success=post_step_result)
            results.append(result)
            if not result.get("ok") and not args.skip_post_results:
                post_result = post_results([result])
                safe_print(json.dumps(post_result, ensure_ascii=True, indent=2))
    finally:
        driver.quit()

    ok_count = sum(1 for result in results if result.get("ok"))
    safe_print("[DONE] AI Remmiter processed groups:", len(results), "success:", ok_count, "failed:", len(results) - ok_count)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        safe_print("[ERROR]", error)
        raise SystemExit(1) from error
