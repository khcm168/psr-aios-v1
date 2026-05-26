# 05 ARM WebApp Doctor

Runs preflight health checks for the ARM Apps Script WebApp endpoints used by daily automation.

Recommended commands:

```cmd
run.cmd --check import
run.cmd --check remmiter
run.cmd --check all
```

Use this launcher when you want a standalone scheduled health check before the live ARM jobs. The `10_ARM_Output` live automation also calls the import check first and warns on failure without blocking the main run.
