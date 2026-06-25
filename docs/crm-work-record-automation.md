# CRM Work Record Automation

This runbook covers `scripts/crm_work_record_lookup.py`, the Selenium automation that creates CRM work records from either a one-off customer lookup or rows in Google Sheet tab `V`.

## Purpose

The script opens the CRM in a visible browser, logs in, opens `工作記錄維護`, clicks `新增`, fills a new work record, saves with `存檔`, and waits until the next blank record is ready.

The current production flow is:

1. Save one standalone test record for customer lookup key `中崙`.
2. Load sheet tab `V` from `地區會議資料V7.0 beta`.
3. Filter rows where column `H` matches the requested date.
4. For each matching row, fill and save `來源代號`, `工作性質代號`, and `紀錄內容`.

This command performs live CRM saves. The default is official sheet-only operation: tab `V` is loaded, today's rows are printed as JSON, and the standalone `中崙` test record is skipped unless `--include-test-record` is passed.

## Environment

The script expects the repo virtual environment and `.env` configuration already used by the project.

Required Google Sheets settings:

- `SERVICE_ACCOUNT_FILE`
- `N1_SOURCE_SPREADSHEET_ID`, falling back to `SPREADSHEET_ID`

Default CRM input can be overridden with `--input-json`, `--company`, and `--customer-name`. Do not commit credentials or local JSON files that contain secrets.

## Sheet Mapping

| Sheet column | Meaning | CRM target |
| --- | --- | --- |
| `H` | Date filter, formatted like `2026/5/26` | Row selection only |
| `O` | Customer/source lookup key | `來源代號` lookup |
| `P` | Work nature text, starting with a code such as `39003` | `工作性質代號` lookup |
| `T` | Work record note | `紀錄內容` textarea |

For `2026/5/26`, tab `V` returned these rows during the successful run:

| Sheet row | Source lookup key | Work nature | Result |
| --- | --- | --- | --- |
| `14928` | `協和` | `39003　　新資料提供` | Saved |
| `14929` | `茂澤` | `39003　　新資料提供` | Saved |

## CRM Control Notes

The current CRM form controls used by the automation are:

| CRM control | Purpose |
| --- | --- |
| `BtnAdd` | `新增` toolbar button |
| `BtnSave` | `存檔` toolbar button |
| `FI024_btn`, `FI024_txt` | `來源代號` lookup button and text field |
| `FI017_btn`, `FI017_txt` | `工作性質代號` lookup button and text field |
| `FI009_txt` | `紀錄內容` textarea |

`FI017` is the work-nature lookup. `FI022` is not the work-nature field in this form.

## Commands

Static check:

```powershell
.\.venv\Scripts\python.exe -m py_compile scripts\crm_work_record_lookup.py
```

Live command for the official sheet workflow. If `--date` is omitted, the script uses today in Asia/Taipei with sheet format `yyyy/m/d`.

```powershell
.\.venv\Scripts\python.exe scripts\crm_work_record_lookup.py --company TOP高峰藥品 --keep-open
```

Replay a specific date:

```powershell
.\.venv\Scripts\python.exe scripts\crm_work_record_lookup.py --company TOP高峰藥品 --date 2026/5/26 --keep-open
```

Include the standalone `中崙` smoke-test before sheet rows:

```powershell
.\.venv\Scripts\python.exe scripts\crm_work_record_lookup.py --company TOP高峰藥品 --include-test-record --keep-open
```

Limit sheet processing during a live proof:

```powershell
.\.venv\Scripts\python.exe scripts\crm_work_record_lookup.py --company TOP高峰藥品 --date 2026/5/26 --max-rows 1 --keep-open
```

Disable sheet loading for lookup/debug-only work:

```powershell
.\.venv\Scripts\python.exe scripts\crm_work_record_lookup.py --company TOP高峰藥品 --no-from-sheet-v --include-test-record --keep-open
```

## Successful Run Evidence

The live run saved:

- Standalone test customer lookup key `中崙`, using default work nature `39003　　新資料提供`.
- Sheet row `14928`, source lookup key `協和`.
- Sheet row `14929`, source lookup key `茂澤`.

After each save, the script accepted normal CRM alert prompts and waited for the next blank/input-ready work record form.

## Troubleshooting

- Use `--browser edge` on this workstation. Chrome previously hit a driver/browser version mismatch.
- If the standalone `中崙` save is rejected for missing `工作性質代號`, confirm the script is using the current default test work nature.
- If a lookup returns no rows, the script stops that record rather than choosing an unrelated result.
- Keep the browser visible when diagnosing frame or dialog behavior; `--keep-open` leaves the browser in its final state.

## File Sync

The project lives under OneDrive:

```text
C:\Users\khcm1\OneDrive\Desktop\Projects\psr-aios-v1
```

Before committing or handing off, confirm OneDrive has finished syncing `scripts/crm_work_record_lookup.py` and this runbook. The repo's operation-log helper can report local OneDrive path context for produced files, but the CRM automation itself does not write a sheet log row.
