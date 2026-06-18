from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env", override=True, encoding="utf-8-sig")

IMPORT_HEALTH_MESSAGE = "ARM Collection import endpoint is available."
IMPORT_CAPABILITY = "collectionImport"
REMMITER_QUEUE_ACTION = "previewAiRemitterQueue"
REMMITER_CAPABILITY = REMMITER_QUEUE_ACTION
HEALTH_TIMEOUT_SECONDS = 30
REMMITER_PREVIEW_TIMEOUT_SECONDS = 120


@dataclass
class CheckResult:
    name: str
    env_var: str
    url: str | None
    ok: bool
    classification: str
    detail: str
    http_status: int | None = None


def safe_print(*values: Any) -> None:
    text = " ".join(str(value) for value in values)
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "utf-8"
        print(text.encode(encoding, errors="backslashreplace").decode(encoding, errors="replace"))


def resolve_import_url() -> tuple[str, str | None]:
    url = os.getenv("ARM_IMPORT_WEBAPP_URL") or os.getenv("ARM_WEBAPP_URL")
    env_var = "ARM_IMPORT_WEBAPP_URL" if os.getenv("ARM_IMPORT_WEBAPP_URL") else "ARM_WEBAPP_URL"
    return env_var, url


def resolve_remmiter_url() -> tuple[str, str | None]:
    url = os.getenv("ARM_REMMITER_WEBAPP_URL") or os.getenv("ARM_WEBAPP_URL")
    env_var = "ARM_REMMITER_WEBAPP_URL" if os.getenv("ARM_REMMITER_WEBAPP_URL") else "ARM_WEBAPP_URL"
    return env_var, url


def classify_json_parse_error(status_code: int, text: str) -> tuple[str, str]:
    if "<html" in text.lower():
        return f"http_{status_code}_html", f"HTTP {status_code} returned HTML instead of JSON."
    return f"http_{status_code}_non_json", f"HTTP {status_code} returned non-JSON content."


def parse_json_response(response: requests.Response) -> tuple[dict[str, Any] | None, str | None, str | None]:
    try:
        body = response.json()
    except ValueError:
        classification, detail = classify_json_parse_error(response.status_code, response.text[:1000])
        return None, classification, detail
    if not isinstance(body, dict):
        return None, "json_not_object", "Response JSON must be an object."
    return body, None, None


def check_import_webapp(session: requests.Session | None = None) -> CheckResult:
    env_var, url = resolve_import_url()
    if not url:
        return CheckResult(
            name="import",
            env_var=env_var,
            url=None,
            ok=False,
            classification="missing_url",
            detail="Missing ARM_IMPORT_WEBAPP_URL and ARM_WEBAPP_URL.",
        )

    client = session or requests.Session()
    try:
        response = client.get(url, timeout=HEALTH_TIMEOUT_SECONDS)
    except requests.RequestException as err:
        return CheckResult(
            name="import",
            env_var=env_var,
            url=url,
            ok=False,
            classification="request_error",
            detail=str(err),
        )

    body, classification, detail = parse_json_response(response)
    if classification:
        return CheckResult(
            name="import",
            env_var=env_var,
            url=url,
            ok=False,
            classification=classification,
            detail=detail or "",
            http_status=response.status_code,
        )

    if response.status_code != 200:
        return CheckResult(
            name="import",
            env_var=env_var,
            url=url,
            ok=False,
            classification=f"http_{response.status_code}",
            detail=f"Expected HTTP 200, got {response.status_code}.",
            http_status=response.status_code,
        )

    if not body.get("ok"):
        return CheckResult(
            name="import",
            env_var=env_var,
            url=url,
            ok=False,
            classification="unexpected_json_error",
            detail="Health endpoint responded with ok=false.",
            http_status=response.status_code,
        )

    if body.get("message") != IMPORT_HEALTH_MESSAGE:
        return CheckResult(
            name="import",
            env_var=env_var,
            url=url,
            ok=False,
            classification="wrong_health_message",
            detail=f"Unexpected health message: {body.get('message')!r}",
            http_status=response.status_code,
        )

    capabilities = set(body.get("capabilities") or [])
    if IMPORT_CAPABILITY not in capabilities:
        return CheckResult(
            name="import",
            env_var=env_var,
            url=url,
            ok=False,
            classification="missing_import_capability",
            detail=f"Endpoint does not declare {IMPORT_CAPABILITY!r}.",
            http_status=response.status_code,
        )

    return CheckResult(
        name="import",
        env_var=env_var,
        url=url,
        ok=True,
        classification="ok",
        detail="Import endpoint contract matched.",
        http_status=response.status_code,
    )


def check_remmiter_webapp(session: requests.Session | None = None) -> CheckResult:
    env_var, url = resolve_remmiter_url()
    if not url:
        return CheckResult(
            name="remmiter",
            env_var=env_var,
            url=None,
            ok=False,
            classification="missing_url",
            detail="Missing ARM_REMMITER_WEBAPP_URL and ARM_WEBAPP_URL.",
        )
    token = os.getenv("ARM_WEBAPP_TOKEN")
    if not token:
        return CheckResult(
            name="remmiter",
            env_var=env_var,
            url=url,
            ok=False,
            classification="missing_token",
            detail="Missing ARM_WEBAPP_TOKEN.",
        )

    payload = {"token": token, "action": REMMITER_QUEUE_ACTION}
    client = session or requests.Session()
    try:
        response = client.post(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=REMMITER_PREVIEW_TIMEOUT_SECONDS,
        )
    except requests.RequestException as err:
        return CheckResult(
            name="remmiter",
            env_var=env_var,
            url=url,
            ok=False,
            classification="request_error",
            detail=str(err),
        )

    body, classification, detail = parse_json_response(response)
    if classification:
        return CheckResult(
            name="remmiter",
            env_var=env_var,
            url=url,
            ok=False,
            classification=classification,
            detail=detail or "",
            http_status=response.status_code,
        )

    if response.status_code != 200:
        return CheckResult(
            name="remmiter",
            env_var=env_var,
            url=url,
            ok=False,
            classification=f"http_{response.status_code}",
            detail=f"Expected HTTP 200, got {response.status_code}.",
            http_status=response.status_code,
        )

    if body.get("ok"):
        return CheckResult(
            name="remmiter",
            env_var=env_var,
            url=url,
            ok=True,
            classification="ok",
            detail="AI Remmiter endpoint contract matched.",
            http_status=response.status_code,
        )

    error = str(body.get("error") or "")
    if "payload.rows must be a non-empty 2D array." in error:
        return CheckResult(
            name="remmiter",
            env_var=env_var,
            url=url,
            ok=False,
            classification="wrong_contract_import_endpoint",
            detail=f"Endpoint is alive but does not route {REMMITER_QUEUE_ACTION!r}.",
            http_status=response.status_code,
        )

    return CheckResult(
        name="remmiter",
        env_var=env_var,
        url=url,
        ok=False,
        classification="apps_script_error",
        detail=error or "Endpoint returned ok=false.",
        http_status=response.status_code,
    )


def print_result(result: CheckResult) -> None:
    safe_print(f"[CHECK] {result.name}")
    safe_print(f"[ENV] {result.env_var}")
    safe_print(f"[URL] {result.url or '<missing>'}")
    if result.http_status is not None:
        safe_print(f"[HTTP] {result.http_status}")
    status = "OK" if result.ok else "FAIL"
    safe_print(f"[{status}] {result.classification}: {result.detail}")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Health-check ARM WebApp endpoints used by daily automation.")
    parser.add_argument(
        "--check",
        choices=("import", "remmiter", "all"),
        default="all",
        help="Select which endpoint contract to verify.",
    )
    return parser


def run_checks(check: str) -> int:
    checks: list[CheckResult] = []
    if check in {"import", "all"}:
        checks.append(check_import_webapp())
    if check in {"remmiter", "all"}:
        checks.append(check_remmiter_webapp())

    passed = 0
    failed = 0
    for result in checks:
        print_result(result)
        if result.ok:
            passed += 1
        else:
            failed += 1

    safe_print(f"[SUMMARY] passed={passed} failed={failed} selected={len(checks)}")
    return 0 if failed == 0 else 1


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()
    raise SystemExit(run_checks(args.check))


if __name__ == "__main__":
    main()
