# ARM WebApp Collection Import Contract

`scripts/arm_export_to_collection.py` posts parsed ARM Excel rows to an Apps Script WebApp before it updates `Collection!B1`. The deployed WebApp source should match `apps_script/61_ARM_WebApp_Endpoint.gs`.

For deployment checks, `.env` encoding issues, mojibake header handling, and post-import triage, see `docs/arm-maintenance-runbook.md`.

## Request

The Python sender posts UTF-8 JSON with this shape:

```json
{
  "token": "shared-secret",
  "rows": [
    [
      "customer_name",
      "invoice_date",
      "invoice_number",
      "closing_number",
      "sales",
      "receivable_amount",
      "unpaid_amount"
    ]
  ]
}
```

Rules:

- `token` must match Apps Script `ScriptProperties.ARM_WEBAPP_TOKEN`.
- `rows` must be a non-empty array.
- Each row must contain exactly 7 string cells in the order above.
- `closing_number` must match `^61\d{2}-\d{10}$`.

The canonical fixture lives at `tests/fixtures/arm_webapp_request.json`.

## Response

Success:

```json
{
  "ok": true,
  "rows": 1,
  "sheetName": "Collection",
  "writeRange": "A3:G3"
}
```

Failure:

```json
{
  "ok": false,
  "error": "Invalid token"
}
```

The Python sender only requires `ok: true` for success. Any missing or falsey `ok` raises a local error using the `error` field.

## Endpoint Behavior

The scaffold in `apps_script/61_ARM_WebApp_Endpoint.gs` validates the request, clears the existing Collection data body, and writes rows starting at `Collection!A3` by default. It intentionally does not update `Collection!B1`; the Python script writes the status sentence after the import succeeds.

Apps Script properties:

- `ARM_WEBAPP_TOKEN`: required shared secret.
- `ARM_COLLECTION_SPREADSHEET_ID`: optional when the script is container-bound; required for standalone deployments.
- `ARM_COLLECTION_SHEET_NAME`: optional, default `Collection`.
- `ARM_COLLECTION_DATA_START_ROW`: optional, default `3`.
- `ARM_COLLECTION_DATA_START_COLUMN`: optional, default `1`.
- `ARM_COLLECTION_CLEAR_COLUMNS`: optional, default `7`.

## Local Validation

Run the ARM contract tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_arm_export_to_collection -v
```

These tests validate the request fixture, response fixture, row-shape guardrails, and presence of the local Apps Script scaffold.
