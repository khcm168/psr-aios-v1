# PSR AIOS Workflow Reference

This document explains the project layout, Python entry points, automation workflows, and rules for future development.

## Project Layout

```text
psr-aios-v1/
  automations/          Numbered human-facing launch folders
  app/                  Reusable Python modules and tested local commands
  scripts/              Legacy-compatible Python scripts and simple launchers
  docs/                 Setup, prompts, and development documentation
  tests/                Unit tests for fragile sheet and workflow assumptions
  data/                 Generated local output folders; artifacts are ignored by git
```

Use `automations/` for daily operation. Use `scripts/` when debugging a specific legacy script directly.

## Numbered Automation Map

| Folder | Purpose | Safe first command | Writes |
| --- | --- | --- | --- |
| `05_ARM_WebApp_Doctor` | Check ARM WebApp reachability and contract matching before live jobs | `run.cmd --check all` | No sheet writes; HTTP health probes only |
| `10_ARM_Output` | Export ARM receivables, import to Collection, update `Collection!B1` status text | `dry_run_existing_excel.cmd path\to\file.xlsx` | Apps Script import and `Collection!B1` |
| `20_CRM_Refresh` | Refresh `CRM` from `List` using `Data_Dictionary` and CRM headers | `dry_run.cmd` | Clears/writes `CRM!A3:R` on live run |
| `30_N1_Sales_LLM` | Generate AI action fields for `List` rows | `preview.cmd` | Writes AI columns only via `writeback.cmd` |
| `40_Visiting_Plan` | Generate `LINE話術` and `拜訪策略` | Run with `--max-rows` first | Writes adjacent output columns in `List` |
| `50_N1_Report_Pack` | Build local markdown/JSON report pack | `run.cmd --max-rows-per-section 5` | Local files only |
| `60_N1_Report_PPT` | Build editable PPTX from report pack JSON | `run.cmd` | Local PPTX only |
| `70_Mothers_Day_Followup` | Build `母親節追蹤` N1 action pack | `run.cmd --max-rows 10` | Local markdown/JSON and log hyperlink |
| `80_Data_Dictionary` | Normalize `Data_Dictionary` and selected `List` headers | Review before running live | Writes `Data_Dictionary` table and one `List` header |

All `.cmd` launchers are repo-relative and prefer `.venv\Scripts\python.exe` when it exists.

## Python Entry Points

### `scripts/arm_export_to_collection.py`

Purpose:
- Opens ARM in Edge, downloads overdue receivables Excel, parses rows, posts them to Apps Script, and updates `Collection!B1`.

Important behavior:
- Excel columns are resolved by header aliases, not fixed positions.
- Valid rows must have a closing number matching `^61\d{2}-\d{10}$`.
- After successful import, writes:

```text
last update in yyyy/mm/dd with XXX rows
```

to `Collection!B1` by default.

Useful commands:

```powershell
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py --excel C:\path\ARM.xlsx --dry-run
.\.venv\Scripts\python.exe scripts\arm_export_to_collection.py --excel C:\path\ARM.xlsx --skip-status-cell
```

Daily automation note:
- `automations/10_ARM_Output/run.cmd` runs `doctor_arm_webapps.py --check import` first.
- A failed preflight prints `[WARN]` and the live import still continues.

Key env vars:
- `ARM_PASSWORD`
- `ARM_IMPORT_WEBAPP_URL`, fallback to `ARM_WEBAPP_URL`
- `ARM_REMMITER_WEBAPP_URL`, fallback to `ARM_WEBAPP_URL`
- `ARM_WEBAPP_TOKEN`
- `ARM_COLLECTION_SPREADSHEET_ID`, fallback to `SPREADSHEET_ID`
- `ARM_COLLECTION_SHEET_NAME`, default `Collection`
- `ARM_COLLECTION_STATUS_CELL`, default `B1`

The Apps Script WebApp request/response contract is documented in `docs/arm-webapp-contract.md`, the maintenance checklist is in `docs/arm-maintenance-runbook.md`, and the local endpoint scaffold is `apps_script/61_ARM_WebApp_Endpoint.gs`.

### `scripts/doctor_arm_webapps.py`

Purpose:
- Verifies the effective ARM import and AI Remmiter WebApp URLs before live automations rely on them.

Useful commands:

```powershell
.\.venv\Scripts\python.exe scripts\doctor_arm_webapps.py --check import
.\.venv\Scripts\python.exe scripts\doctor_arm_webapps.py --check remmiter
.\.venv\Scripts\python.exe scripts\doctor_arm_webapps.py --check all
```

Behavior:
- `import` expects the ARM import health JSON from the WebApp root.
- `remmiter` sends the modern, read-only `previewAiRemitterQueue` request and
  fails clearly if the endpoint is actually an import-only handler.
- Exit code `0` means all selected checks passed; non-zero means at least one failed.

The canonical deployment and client registry are owned by `C:\Dev\psr-gas`.
Run `automations\05_ARM_WebApp_Doctor\sync_config.cmd` to audit this project's
URL variables, or add `--apply` after a reviewed deployment change. The ARM
project owns live direct remittance; the legacy `scripts\collection_ai_remmiter.py`
flow is not the deployment contract for new integrations.

### `scripts/CRM.py`

Purpose:
- Builds the `CRM` sheet from `List` rows marked Top30.

Important behavior:
- Reads source columns from `List` row 2 using `Data_Dictionary`.
- Aligns output to the current CRM header row.
- Prints progress for every processed Top30 row.
- Uses Ollama for concise story notes unless `--skip-ollama` is passed.

Useful commands:

```powershell
.\.venv\Scripts\python.exe scripts\CRM.py --dry-run --max-rows 5 --skip-ollama
.\.venv\Scripts\python.exe scripts\CRM.py --skip-ollama
.\.venv\Scripts\python.exe scripts\CRM.py
```

Live write:
- Clears `CRM!A3:{last column}`.
- Writes generated rows starting at `CRM!A3`.

### `scripts/N1salesLLM.py`

Purpose:
- Generates AI recommendation fields for selected `List` rows.

Important behavior:
- Direct execution is safe preview by default.
- `--writeback` is required to write AI result fields.
- Writeback columns are validated before the first write.
- Prompt is JSON-only Traditional Chinese and uses Ollama `format: json`.

Useful commands:

```powershell
.\.venv\Scripts\python.exe scripts\N1salesLLM.py --start-row 23 --max-rows 1
.\.venv\Scripts\python.exe scripts\N1salesLLM.py --start-row 23 --max-rows 5 --writeback
.\.venv\Scripts\python.exe scripts\N1salesLLM.py --debug --start-row 23
```

Writes:
- `ai_action_proposal`
- `ai_recommended_product`
- `ai_product_reason`
- `ai_proposed_line`
- `ai_visit_angle`

### `scripts/visitingplan.py`

Purpose:
- Generates customer-facing LINE text and visit strategy text.

Important behavior:
- Source columns are resolved from `List` row 2 headers.
- Output columns are resolved by headers:
  - `LINE話術`
  - `拜訪策略`
- These two output columns must remain adjacent.
- Prompt text lives in `docs/prompts/visitingplan.md`.

Useful command:

```powershell
.\.venv\Scripts\python.exe scripts\visitingplan.py --start-row 3 --max-rows 5
```

### `scripts/normalize_data_dictionary.py`

Purpose:
- Normalizes `Data_Dictionary` keys, fills `write_policy`, and cleans the second Key man `List` header.

Important behavior:
- Finds the dictionary table by header block; it does not assume `H:N`.
- Writes the normalized dictionary table back to the detected location.

### `app/mothers_day_followup.py`

Purpose:
- Reads `母親節追蹤` from `地區會議資料V7.0 beta`, selects open N1 follow-up rows, classifies them, and generates actionable Traditional Chinese outreach.

Important behavior:
- Optimized for `追蹤中`, `鼓勵自用體驗`, and `擴量中`.
- Handles the real tab shape where status may be an unnamed fifth column.
- Writes local markdown/JSON and logs a hyperlink to the markdown result.

Useful command:

```powershell
.\.venv\Scripts\python.exe -m app.mothers_day_followup --max-rows 10
```

### `app/n1_report_pack.py`

Purpose:
- Builds local markdown/JSON source packs from tabs in `地區會議資料V7.0 beta`.

Important behavior:
- Detects section headers inside each tab.
- Writes local files to `data/report_packs/`.
- Generated artifacts are ignored by git.

### `app/n1_report_ppt.py`

Purpose:
- Builds an editable PowerPoint draft from a local report-pack JSON file.

Useful command:

```powershell
.\.venv\Scripts\python.exe -m app.n1_report_ppt
```

### `app/operation_log.py`

Purpose:
- Builds and appends rows to the `log` worksheet.

Important behavior:
- Report-producing workflows can write a clickable `=HYPERLINK(...)` formula in `details`.
- OneDrive synced file paths are recorded in `variables_json` when local files are produced.

## Standard Run Order

When changing code:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall app scripts tests
```

When testing sheet-writing jobs:

1. Run dry-run or preview mode first.
2. Confirm printed target ranges.
3. Run live with the smallest useful `--max-rows`.
4. Check `log`.
5. Run the full live job only after the small run looks correct.

## Column Safety Rules

- Prefer header lookup over fixed column letters.
- Prefer `Data_Dictionary` internal keys for `List` mappings.
- Fixed cells are allowed only when they are intentional layout cells, such as `Collection!B1`.
- If a script writes by column letter, it must first compute that letter from the current header row.
- Before live writes, print or log the target range.

## Git Rules

Do commit:
- Python source files
- Tests
- Numbered automation launchers
- Documentation
- `.gitkeep` placeholders

Do not commit:
- `.env`
- `secrets/`
- `.venv/`
- `.deps/`
- generated report packs
- local token/scratch scripts
- `__pycache__/`

Recommended commit flow:

```powershell
git status --short
git add <intended files>
git diff --name-only --cached
git commit -m "Short action-oriented summary"
```

## Future Development Checklist

For every new automation:

- Add a numbered folder in `automations/NN_Name`.
- Add `README.md` in that folder.
- Add `run.cmd`; add `dry_run.cmd` or `preview.cmd` if the workflow can write.
- Keep paths repo-relative.
- Add tests for moved columns or fragile assumptions.
- Log rows processed, target ranges, and output file links where relevant.
- Run unit tests and compile checks before committing.
