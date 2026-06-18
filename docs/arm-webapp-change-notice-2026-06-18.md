# ARM Google WebApp Client Notice - 2026-06-18

This project uses shared Apps Script deployment:

```text
AKfycbwLNOVxJlC6e18PVZJ-KzzZu63SfadIUnSyfohzybE0RA1hduKZWHW2C0jYDfSe1gTDxA
```

The deployment was updated in place to version `36`; its `/exec` URL remains
unchanged. It serves ARM Collection import, direct-run remittance, lock
management, and optional Mesh capabilities against production spreadsheet
`1eTnZppbhu7fpwdFTrnFoQmxchylsZus0Sw4j1t61Zzo`, sheet `Collection`.

Version `36` adds machine-readable `contract`, `contractVersion`,
`releaseVersion`, and `deploymentId` health fields. The canonical registry and
configuration orchestrator live in `C:\Dev\psr-gas`:

```cmd
automations\05_ARM_WebApp_Doctor\sync_config.cmd
automations\05_ARM_WebApp_Doctor\sync_config.cmd --apply
```

The orchestrator validates the live endpoint before changing non-secret URL
variables. It never copies or prints `ARM_WEBAPP_TOKEN`.

Before a live import, run:

```powershell
.\.venv\Scripts\python.exe scripts\doctor_arm_webapps.py --check all
```

Do not reuse this deployment for a different spreadsheet. Register a separate
deployment with its own explicit target instead.
