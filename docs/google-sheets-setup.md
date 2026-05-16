# Google Sheets setup

1. Create or choose a Google Sheet.
2. Copy the sheet ID from the URL. It is the long value between `/d/` and `/edit`.
3. Create a Google Cloud service account and download its JSON key.
4. Save the key somewhere ignored by git, for example `secrets/google-service-account.json`.
5. Share the Google Sheet with the service account email from the JSON key.
6. Copy `.env.example` to `.env` and fill in the real values.

Run a local smoke test without touching Google:

```powershell
python -m app.main --dry-run --message "hello sheets"
```

Run the real append:

```powershell
python -m app.main --message "hello sheets"
```

## N1 report pack access

For `n1_report_pack`, share the active workbook `地區會議資料V7.0 beta` with the same service account email. Set `N1_SOURCE_SPREADSHEET_ID` to that workbook ID. The report spreadsheet IDs are also configurable so the generated JSON pack can record the intended downstream sources:

```powershell
N1_SOURCE_SPREADSHEET_ID=replace-with-district-meeting-data-sheet-id
N1_WEEKLY_REPORT_SPREADSHEET_ID=replace-with-n1-weekly-report-sheet-id
N1_OPERATIONS_REPORT_SPREADSHEET_ID=replace-with-n1-operations-report-sheet-id
```

Then run:

```powershell
.\scripts\n1_report_pack.ps1
```
