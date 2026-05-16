# PSR AIOS v1

Python starter project for Google Sheets automations.

## What this codebase does

This repo is intentionally small. It gives you a clean place to build scheduled or manual Python jobs that read from, transform, and write to Google Sheets.

- `automations/` contains numbered, human-facing launch folders such as `10_ARM_Output` and `20_CRM_Refresh`.
- `app/main.py` is the command-line entry point.
- `app/config.py` loads required settings from `.env`.
- `app/sheets.py` wraps Google Sheets access behind a small client.
- `app/automation.py` contains starter automation logic that is easy to test.
- `tests/` contains fast unit tests that do not call Google APIs.
- `docs/google-sheets-setup.md` explains how to connect a real Sheet.
- `docs/development-rules.md` records the project rules for future automation work.
- `docs/workflow-reference.md` explains every Python workflow, launcher, write target, and safe-run command.

## Automation Map

Use the numbered folders in `automations/` for day-to-day runs:

```text
10_ARM_Output              ARM export/import plus Collection!C1 status
20_CRM_Refresh             Refresh CRM from List
30_N1_Sales_LLM            Preview/write back N1 AI suggestions
40_Visiting_Plan           Generate LINE話術 and 拜訪策略
50_N1_Report_Pack          Build N1 markdown/JSON report pack
60_N1_Report_PPT           Build editable PPTX from report pack
70_Mothers_Day_Followup    Build 母親節追蹤 action pack
80_Data_Dictionary         Normalize Data_Dictionary
```

The old `scripts/` entry points remain for compatibility, but new human-facing launchers should use the numbered folders.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env`, then run a dry run:

```powershell
python -m app.main --dry-run --message "hello sheets"
```

Run a focused Google Sheets write probe:

```powershell
python -m app.sheet_log_probe --dry-run --message "testing sheet log append"
python -m app.sheet_log_probe --message "testing sheet log append" --verify
```

Python operations write tracking records to the `log` worksheet. Each log row records:

```text
occurred_at | project | operation | result | purpose | variables_json | details | host | user
```

Report-producing jobs write a clickable result link in `details`. When the repo is inside a synced folder such as OneDrive, `variables_json` also records the absolute markdown/JSON paths plus sync context so you can tell whether the link points at a local synced file.

## Prompt Templates

`scripts/visitingplan.py` reads its editable prompt from:

```text
docs/prompts/visitingplan.md
```

Keep the placeholders unchanged when tuning the prompt:

```text
{region}
{customer_name}
{history_sales}
{visit_notes}
```

After Google credentials are configured and the sheet is shared with the service account:

```powershell
python -m app.main --message "hello sheets"
```

The starter app appends a row with:

1. UTC timestamp
2. source project name
3. message

If the configured worksheet does not exist, it creates the worksheet and writes a header row first.

## N1 report pack

The local `n1_report_pack` command reads the workbook named `地區會議資料V7.0 beta` and writes a compact markdown pack plus a JSON source pack for:

- `N1 週報 2026-04-27`
- `N1 地區業績營運報告 2026-04-27`

Configure the source and report spreadsheet IDs in `.env`:

```powershell
N1_SOURCE_SPREADSHEET_ID=replace-with-district-meeting-data-sheet-id
N1_SOURCE_WORKBOOK_TITLE=地區會議資料V7.0 beta
N1_WEEKLY_REPORT_SPREADSHEET_ID=replace-with-n1-weekly-report-sheet-id
N1_OPERATIONS_REPORT_SPREADSHEET_ID=replace-with-n1-operations-report-sheet-id
N1_REPORT_PACK_OUTPUT_DIR=data/report_packs
GOOGLE_APPLICATION_CREDENTIALS=secrets/google-service-account.json
```

Existing local names also work: `SPREADSHEET_ID` for the source workbook and `SERVICE_ACCOUNT_FILE` for the service account JSON path.

Share the source workbook with the service account email, then run:

```powershell
.\scripts\n1_report_pack.ps1
```

or:

```powershell
python -m app.n1_report_pack
```

By default it pulls `Action Plan 進度`, `本月行動計畫`, `今日拜訪`, and `反映事項`, then writes:

```text
data/report_packs/n1_report_pack_2026-04-27.md
data/report_packs/n1_report_pack_2026-04-27.json
```

Useful overrides:

```powershell
.\scripts\n1_report_pack.ps1 --date 2026-04-27 --tab "今日拜訪" --tab "反映事項" --max-rows-per-section 20
```

Create an editable PowerPoint draft from the JSON pack:

```powershell
.\scripts\n1_report_ppt.ps1
```

This writes:

```text
data/report_packs/N1_report_2026-04-27.pptx
```

## Mother’s Day N1 follow-up pack

The `mothers_day_followup` command reads the `母親節追蹤` tab in `地區會議資料V7.0 beta`, pulls still-open N1 rows for:

- `追蹤中`
- `鼓勵自用體驗`
- `擴量中`

It classifies each row and writes concise Traditional Chinese LINE outreach plus the next visit step. The tone follows the existing `visitingplan.py` guidance: low pressure, trust-oriented, and clear enough for immediate action.

Run:

```powershell
.\scripts\mothers_day_followup.ps1
```

This writes:

```text
data/mothers_day_followup/mothers_day_followup_YYYY-MM-DD.md
data/mothers_day_followup/mothers_day_followup_YYYY-MM-DD.json
```

Useful overrides:

```powershell
.\scripts\mothers_day_followup.ps1 --max-rows 20
.\scripts\mothers_day_followup.ps1 --include-other-open
.\scripts\mothers_day_followup.ps1 --status 追蹤中 --status 擴量中
```

## Test

```powershell
python -m unittest discover -s tests
```

## Environment variables

See `.env.example`.

- `PROJECT_NAME`: Label written into the sheet.
- `GOOGLE_SHEET_ID`: Target spreadsheet ID.
- `GOOGLE_WORKSHEET_NAME`: Target worksheet tab. Defaults to `log`.
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to a Google service account JSON key.
- `SPREADSHEET_ID`: Existing-script alias for the source spreadsheet ID.
- `SERVICE_ACCOUNT_FILE`: Existing-script alias for the service account JSON key.
- `CRM_DESTINATION_SPREADSHEET_ID`: Optional CRM refresh destination spreadsheet ID. Leave blank to default to `SPREADSHEET_ID`; the script reads `List` and `Data_Dictionary` from the source workbook and writes the `CRM` rows and operation log to this destination.
- `N1_SOURCE_SPREADSHEET_ID`: Source workbook ID for `地區會議資料V7.0 beta`.
- `N1_SOURCE_WORKBOOK_TITLE`: Expected source workbook title.
- `N1_WEEKLY_REPORT_SPREADSHEET_ID`: Optional ID for the `N1 週報` destination/reference sheet.
- `N1_OPERATIONS_REPORT_SPREADSHEET_ID`: Optional ID for the `N1 地區業績營運報告` destination/reference sheet.
- `N1_REPORT_PACK_OUTPUT_DIR`: Local output directory for markdown and JSON packs.
- `MOTHERS_DAY_FOLLOWUP_TAB`: Source tab for the Mother’s Day follow-up automation. Defaults to `母親節追蹤`.
- `MOTHERS_DAY_FOLLOWUP_OUTPUT_DIR`: Local output directory for Mother’s Day markdown and JSON packs.

## Next automation ideas

- Read an input worksheet and write processed results to an output worksheet.
- Add a scheduler such as Windows Task Scheduler, cron, GitHub Actions, or Cloud Run.
- Replace `build_status_row` with your business workflow.
- Add logging, retries, and alerting once the workflow becomes production-facing.
