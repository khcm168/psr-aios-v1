# 20 CRM Refresh

Refreshes the `CRM` sheet from `List`, using `Data_Dictionary` and the current CRM header row.

Recommended first run:

```cmd
dry_run.cmd
```

Live run:

```cmd
run.cmd
```

Column policy: source and target columns are resolved by headers. `Data_Dictionary` is found by its header block, not by a fixed `H:N` range.
