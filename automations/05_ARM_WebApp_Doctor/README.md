# 05 ARM WebApp Doctor

Runs preflight health checks for the ARM Apps Script WebApp endpoints used by daily automation.

Recommended commands:

```cmd
run.cmd --check import
run.cmd --check remmiter
run.cmd --check all
```

Use this launcher when you want a standalone scheduled health check before the live ARM jobs. The `10_ARM_Output` live automation also calls the import check first and warns on failure without blocking the main run.

The shared deployment registry and orchestrator live in canonical `C:\Dev\psr-gas`.
Audit this project's URL configuration with:

```cmd
sync_config.cmd
```

After a reviewed deployment change, verify the new endpoint and normalize the
non-secret URL variables in `.env` with:

```cmd
sync_config.cmd --apply
```

The orchestrator never reads, prints, or copies `ARM_WEBAPP_TOKEN`.

Release 37 adds sequential project probes and a structured spreadsheet audit
row. See `docs\arm-webapp-orchestration.md` for the proven workflow, evidence,
failure rules, and rollback procedure.
