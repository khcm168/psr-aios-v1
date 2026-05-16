# 10 ARM Output

Exports ARM overdue receivables, imports the parsed rows to the Collection workflow, then updates `Collection!C1` with:

```text
last update in yyyy/mm/dd with XXX rows
```

Use `run.cmd` for the live browser export/import. Use `dry_run_existing_excel.cmd` when you want to validate an already-downloaded Excel file without posting rows.

Column policy: ARM Excel columns are resolved by header aliases before rows are sent.
