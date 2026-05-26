# 10 ARM Output

Exports ARM overdue receivables, imports the parsed rows to the Collection workflow, then updates `Collection!B1` with:

```text
last update in yyyy/mm/dd with XXX rows
```

Use `run.cmd` for the live browser export/import. Use `dry_run_existing_excel.cmd` when you want to validate an already-downloaded Excel file without posting rows.

`run.cmd` now calls the ARM WebApp doctor first in import mode. If the preflight fails, it prints `[WARN]` and still continues into the live ARM run.

Column policy: ARM Excel columns are resolved by header aliases before rows are sent.

The Apps Script WebApp contract is now local in `docs/arm-webapp-contract.md`, with deployable scaffold source at `apps_script/61_ARM_WebApp_Endpoint.gs`.
