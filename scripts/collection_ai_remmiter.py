from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ARM_LOGIN_URL = os.getenv("ARM_LOGIN_URL", "http://192.168.0.187/BPMPlus/#/passport/login")
ARM_RECEIVABLE_URL = os.getenv("ARM_RECEIVABLE_URL", "http://192.168.0.187/BPMPlus/#/arm/armr01")

ARM_ACCOUNT = os.getenv("ARM_ACCOUNT", "108010")
ARM_PASSWORD = os.getenv("ARM_PASSWORD")
ARM_REMMITER_WEBAPP_URL = os.getenv("ARM_REMMITER_WEBAPP_URL") or os.getenv("ARM_WEBAPP_URL")
ARM_WEBAPP_TOKEN = os.getenv("ARM_WEBAPP_TOKEN")
ARM_BROWSER = os.getenv("ARM_BROWSER", "edge").strip().lower()

DEBUG_DIR = Path(os.getenv("ARM_DEBUG_DIR", r"C:\ARM_Debug"))

ACTION_GET_QUEUE = "getAiRemmiterQueue"
ACTION_RECORD_RESULTS = "recordAiRemmiterResults"
CLOSING_NO_RE = re.compile(r"^61\d{2}-\d{10}$")


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
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    if ARM_BROWSER == "chrome":
        options = ChromeOptions()
        options.add_argument("--start-maximized")
        return webdriver.Chrome(options=options)

    options = EdgeOptions()
    options.add_argument("--start-maximized")
    return webdriver.Edge(options=options)


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
    response.raise_for_status()
    result = response.json()
    if not result.get("ok"):
        raise RuntimeError("Apps Script error: " + str(result.get("error")))
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
    time.sleep(0.2)

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
    time.sleep(0.2)
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
    time.sleep(1)
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
    time.sleep(4)
    save_debug(driver, "ai_remmiter_after_login")
    safe_print("[OK] Login submitted")


def open_arm_receivables(driver, wait: WebDriverWait) -> None:
    safe_print("[STEP] Open ARM receivables page")
    driver.get(ARM_RECEIVABLE_URL)
    wait_document_ready(driver)
    time.sleep(4)
    save_debug(driver, "ai_remmiter_armr01")

    detail_xpath = (
        "//span[contains(@class, 'ng-star-inserted') and "
        "(contains(normalize-space(.), '\u9ede\u6211\u89c0\u770b\u660e\u7d30') or contains(normalize-space(.), '\u89c0\u770b\u660e\u7d30'))]"
    )

    try:
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.XPATH, detail_xpath)))
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
        time.sleep(5)
        save_debug(driver, "ai_remmiter_after_click_receivables_menu")

    safe_print("[STEP] Click \u9ede\u6211\u89c0\u770b\u660e\u7d30")
    click_first(driver, wait, [detail_xpath], "\u9ede\u6211\u89c0\u770b\u660e\u7d30")
    time.sleep(5)
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
    time.sleep(0.2)
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
    time.sleep(0.2)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    return element


def wait_for_dialogs_to_close(driver) -> None:
    try:
        WebDriverWait(driver, 10).until(lambda current_driver: not find_visible_dialogs(current_driver))
    except TimeoutException:
        pass


def click_followup_confirm(driver, item: dict[str, Any], step_name: str, closing_no: str) -> None:
    time.sleep(0.5)

    try:
        alert = WebDriverWait(driver, 2).until(EC.alert_is_present())
        save_debug(driver, debug_name(item, step_name + "_confirm_alert", closing_no))
        alert.accept()
        time.sleep(1)
        wait_for_dialogs_to_close(driver)
        return
    except TimeoutException:
        pass

    click_confirmation_only_dialog_ok(driver, WebDriverWait(driver, 10))
    save_debug(driver, debug_name(item, step_name + "_confirm_ok_clicked", closing_no))
    time.sleep(1.5)
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
    time.sleep(0.2)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)
    time.sleep(0.8)
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
    time.sleep(0.2)
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
    time.sleep(0.8)
    fill_closing_no(driver, wait, closing_no)
    click_ok(driver, wait)
    time.sleep(2)


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
    time.sleep(0.5)
    click_today_link(driver, wait)
    time.sleep(0.5)


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
    result["message"] = "Cash amount submitted and confirmed."
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
    result["message"] = "COD discount return date submitted and confirmed."
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


def run_group(driver, wait: WebDriverWait, item: dict[str, Any]) -> dict[str, Any]:
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

        if item.get("codStep"):
            cod_result = run_cod_step(driver, wait, item, item["codStep"])
            result["steps"].append(cod_result)
            if not cod_result.get("ok"):
                result["message"] = cod_result.get("message") or "COD step failed."
                return result

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
    parser.add_argument("--limit", type=int, help="Process only the first N checked groups.")
    parser.add_argument("--skip-post-results", action="store_true", help="Do not write final TRUE/FALSE results back to Collection!U.")
    args = parser.parse_args()

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
    wait = WebDriverWait(driver, 30)
    try:
        login_arm(driver, wait)
        open_arm_receivables(driver, wait)
        results = [run_group(driver, wait, item) for item in items]
    finally:
        driver.quit()

    if not args.skip_post_results:
        post_result = post_results(results)
        safe_print(json.dumps(post_result, ensure_ascii=True, indent=2))

    ok_count = sum(1 for result in results if result.get("ok"))
    safe_print("[DONE] AI Remmiter processed groups:", len(results), "success:", ok_count, "failed:", len(results) - ok_count)


if __name__ == "__main__":
    main()
