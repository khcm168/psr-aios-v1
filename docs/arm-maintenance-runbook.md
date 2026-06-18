# ARM Collection Import Maintenance Runbook

Current shared-deployment notice:
`docs/arm-webapp-change-notice-2026-06-18.md`.

This runbook is for maintaining the ARM receivables export/import flow used by `scripts/arm_export_to_collection.py`. It records the practical failure modes seen during maintenance so the next repair starts from known ground instead of rediscovering the same traps.

## Moving Parts

There are three systems involved:

- Local Python project: `psr-aios-v1`, especially `scripts/arm_export_to_collection.py`, `.env`, and `tests/test_arm_export_to_collection.py`.
- Apps Script project: `psr-gas`, especially the deployed Web App endpoint in `61_ARM_WebApp_Endpoint.js`.
- Google Sheets / service account access: used only for the optional local update of `Collection!B1` after the Apps Script import succeeds.

Keep these separate in your head. A successful Apps Script Web App import does not mean local git is committed. A committed Python change does not mean the Apps Script deployment has been updated.

## Normal Success Path

The intended flow is:

1. Python opens ARM or reads an existing ARM Excel file.
2. Python parses ARM receivable rows.
3. Python POSTs rows to the Apps Script Web App URL from `ARM_IMPORT_WEBAPP_URL`, falling back to `ARM_WEBAPP_URL` for older setups.
4. Apps Script validates `ARM_WEBAPP_TOKEN` and writes the `Collection` data body.
5. Apps Script preserves/updates Collection status/archive behavior.
6. Python optionally updates `Collection!B1` with `last update in yyyy/mm/dd with N rows` using a Google service account.

The data import is step 4. The `Collection!B1` update is useful, but it must not be treated as proof that the import failed if it has a credential problem after step 4 succeeds.

## Daily Commands

Standalone preflight doctor:

```powershell
.\.venv\Scripts\python.exe scripts\doctor_arm_webapps.py --check all
```

Parse only, with no ARM browser and no cloud writes:

```powershell
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py --excel C:\ARM_Downloads\arm-export.xls --dry-run
```

Import from an existing Excel file and skip only the optional `Collection!B1` service-account update:

```powershell
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py --excel C:\ARM_Downloads\arm-export.xls --skip-status-cell
```

Full import from an existing Excel file:

```powershell
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py --excel C:\ARM_Downloads\arm-export.xls
```

Full browser export plus import:

```powershell
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py
```

Daily launcher behavior:

- `automations/10_ARM_Output/run.cmd` runs `doctor_arm_webapps.py --check import` first.
- If the preflight fails, the launcher prints `[WARN]` and still continues into the live ARM import.
- Use `automations/05_ARM_WebApp_Doctor/run.cmd` when you want a standalone scheduled health check.

Run local contract tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_arm_export_to_collection -v
```

## Environment Variables

The script loads `psr-aios-v1\.env` using `override=True` and `encoding="utf-8-sig"`. This is intentional:

- `override=True` lets the project `.env` replace stale Windows user environment values.
- `utf-8-sig` tolerates a UTF-8 BOM if a Windows editor or PowerShell writes one again.

Required for import:

```text
ARM_IMPORT_WEBAPP_URL=https://script.google.com/macros/s/<web-app-deployment-id>/exec
ARM_WEBAPP_TOKEN=<same token as Apps Script ScriptProperties.ARM_WEBAPP_TOKEN>
```

Backward-compatible fallback:

```text
ARM_WEBAPP_URL=https://script.google.com/macros/s/<shared-web-app-deployment-id>/exec
```

Required only for the optional `Collection!B1` status-cell update:

```text
SERVICE_ACCOUNT_FILE=C:\path\to\service-account.json
SPREADSHEET_ID=<Collection spreadsheet id>
```

Optional overrides:

```text
ARM_COLLECTION_SPREADSHEET_ID=<Collection spreadsheet id, overrides SPREADSHEET_ID>
ARM_COLLECTION_SHEET_NAME=Collection
ARM_COLLECTION_STATUS_CELL=B1
ARM_DOWNLOAD_DIR=C:\ARM_Downloads
ARM_DEBUG_DIR=C:\ARM_Debug
```

AI Remmiter setup:

```text
ARM_REMMITER_WEBAPP_URL=https://script.google.com/macros/s/<remmiter-web-app-deployment-id>/exec
```

Shared fallback policy:

- `ARM_WEBAPP_URL` is legacy fallback only.
- New deployments should be assigned to `ARM_IMPORT_WEBAPP_URL` or `ARM_REMMITER_WEBAPP_URL` explicitly.
- Keep the current mapping in `docs/arm-webapp-deployments.md`.

Never commit real `.env`, tokens, passwords, or service-account JSON keys.

## Apps Script Deployment: Web App vs API Executable

Python requires a Web App deployment URL:

```text
https://script.google.com/macros/s/<deployment-id>/exec
```

Do not use the API executable URL for Python:

```text
https://script.googleapis.com/v1/scripts/<deployment-id>:run
```

A deployment can expose both labels in the Apps Script UI, but Python must use the Web App URL. If the wrong deployment type/id is used, `requests.post()` usually receives a Google HTML 404 page.

Health check the Web App URL before debugging Python:

```powershell
$url = if ($env:ARM_IMPORT_WEBAPP_URL) { $env:ARM_IMPORT_WEBAPP_URL } else { $env:ARM_WEBAPP_URL }
Invoke-WebRequest -Uri $url -UseBasicParsing
```

Expected response:

```json
{"ok":true,"message":"ARM Collection import endpoint is available."}
```

If this returns 404, fix the Apps Script Web App deployment or `ARM_IMPORT_WEBAPP_URL` first. The Excel parser is not the problem.

## Token Checks

If the Web App health check succeeds but POST returns unauthorized or an Apps Script JSON error, check the shared token:

- Windows/project side: `ARM_WEBAPP_TOKEN` in `.env`.
- Apps Script side: Script Property `ARM_WEBAPP_TOKEN`.

Use `rotateArmWebAppToken()` only when intentionally rotating the token. After rotation, copy the new value into `.env`; do not commit the token.

## Encoding and Mojibake

ARM Excel exports and Windows tooling can produce mixed or ambiguous encodings. Two different encoding problems matter here.

### UTF-8 BOM

A UTF-8 BOM is the hidden byte prefix `EF BB BF`. If it appears at the start of `.env`, the first key can be read as `\ufeffSERVICE_ACCOUNT_FILE` instead of `SERVICE_ACCOUNT_FILE`, causing this misleading error:

```text
Missing environment variables: SERVICE_ACCOUNT_FILE or GOOGLE_APPLICATION_CREDENTIALS
```

Check for a BOM:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; b=Path('.env').read_bytes()[:3]; print(b, b == b'\xef\xbb\xbf')"
```

Rewrite `.env` as UTF-8 without BOM if needed. The script also uses `encoding="utf-8-sig"` so a future BOM is tolerated.

### Mojibake Headers

Mojibake is text decoded with the wrong encoding. ARM column headers may appear either as readable Chinese or as garbled strings. The parser must support both.

Do not "clean up" garbled header aliases just because they look ugly. They may be compatibility aliases for real ARM exports. Instead:

- Keep readable Chinese names as canonical `SOURCE_COLS` where possible.
- Keep ARM-export mojibake strings in `HEADER_ALIASES`.
- Add or update tests whenever a new exported header variant appears.

The parser should resolve columns by aliases, never by fixed positions.

## Service Account and Clock Issues

The optional status-cell update uses Google Sheets API credentials. If import succeeds but the status update warns with this error:

```text
invalid_grant: Invalid JWT: Token must be a short-lived token (60 minutes) and in a reasonable timeframe.
```

then the service-account JSON was found, but Google rejected the JWT timestamp. Common causes:

- Windows system clock is not synchronized.
- Timezone/time settings are stale after sleep or VM/container context changes.
- The service account key is old or revoked, less common than clock skew.

First fix clock sync:

```powershell
Get-Date -Format o
w32tm /query /status
```

Then use Windows Date & Time settings to sync the clock. After the clock is correct, retry only the status-cell update if needed:

```powershell
.\.venv\Scripts\python.exe -c "from scripts.arm_export_to_collection import update_collection_status_cell; update_collection_status_cell(220)"
```

If clock sync is fine and it still fails, verify that the service account JSON exists and that the target spreadsheet is shared with the service account email.

## Failure Triage

Use this order. It saves time.

1. Web App alive?

```powershell
$url = if ($env:ARM_IMPORT_WEBAPP_URL) { $env:ARM_IMPORT_WEBAPP_URL } else { $env:ARM_WEBAPP_URL }
Invoke-WebRequest -Uri $url -UseBasicParsing
```

Or run the dedicated doctor:

```powershell
.\.venv\Scripts\python.exe scripts\doctor_arm_webapps.py --check import
```

2. Python sees the expected config?

```powershell
.\.venv\Scripts\python.exe -c "import scripts.arm_export_to_collection as m; print(m.ARM_IMPORT_WEBAPP_URL); print(m.SERVICE_ACCOUNT_FILE); print(m.ARM_COLLECTION_SPREADSHEET_ID)"
```

3. Excel parse works?

```powershell
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py --excel C:\ARM_Downloads\arm-export.xls --dry-run
```

4. Import works without status-cell update?

```powershell
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py --excel C:\ARM_Downloads\arm-export.xls --skip-status-cell
```

5. Full run works?

```powershell
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py --excel C:\ARM_Downloads\arm-export.xls
```

Interpretation:

- 404 HTML page: wrong/dead Web App deployment URL.
- Unauthorized JSON error: token mismatch.
- Missing `SERVICE_ACCOUNT_FILE`: `.env` missing, stale process env, or BOM at start of `.env`.
- `invalid_grant` JWT timeframe: clock sync or service-account key issue.
- Missing required columns: ARM header alias drift; update aliases and tests.

## Post-Cloud-Test Sync

After any successful Apps Script Web App POST or `clasp push`, remember that Apps Script cloud and git are separate systems.

In the Apps Script repo:

```powershell
npx.cmd clasp status
git status --short --branch
```

In the Python repo:

```powershell
git status --short --branch
```

If the cloud-tested behavior depends on local changes, commit and push those changes. Otherwise future worktrees may start from older git state and drift from the working cloud version.

## Maintenance Rules

- Do not commit `.env`, service-account JSON files, passwords, or tokens.
- Do not replace a Web App URL with an API executable URL.
- Do not remove mojibake aliases unless tests prove they are unused and a real ARM export still parses.
- Do not treat `Collection!B1` update failure as an import failure after Apps Script returns `ok: true`.
- Prefer tests and small health checks before rerunning a full ARM browser automation.
- When editing files with Chinese text on Windows, verify no BOM and run `py_compile` plus the ARM unit tests.
