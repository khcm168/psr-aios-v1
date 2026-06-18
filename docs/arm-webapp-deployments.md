# ARM WebApp Deployment Registry

The machine-readable source of truth is
`C:\Dev\psr-gas\arm_webapp_registry.json`. Do not repoint a client URL from
memory.

## Production shared endpoint

```text
scriptId=199VYDwi4DHWaITv48vO1mri4i20C9CJ0euOsvEs3dHwUfNrwlBF02t6x
deploymentId=AKfycbwLNOVxJlC6e18PVZJ-KzzZu63SfadIUnSyfohzybE0RA1hduKZWHW2C0jYDfSe1gTDxA
version=37
url=https://script.google.com/macros/s/AKfycbwLNOVxJlC6e18PVZJ-KzzZu63SfadIUnSyfohzybE0RA1hduKZWHW2C0jYDfSe1gTDxA/exec
contract=ARM Shared WebApp API 2.0.0
webapp.executeAs=USER_DEPLOYING
webapp.access=ANYONE_ANONYMOUS
```

The endpoint is token-protected and explicitly tied to production spreadsheet
`1eTnZppbhu7fpwdFTrnFoQmxchylsZus0Sw4j1t61Zzo`, sheet `Collection`.

All three URL variables in this project should resolve to the production URL:

```text
ARM_WEBAPP_URL
ARM_IMPORT_WEBAPP_URL
ARM_REMMITER_WEBAPP_URL
```

Audit configuration with:

```cmd
automations\05_ARM_WebApp_Doctor\sync_config.cmd
```

Use `--apply` only after the orchestrator confirms the live contract and
capabilities. Tokens remain private in each project's `.env` and Apps Script
Script Properties.

Release 37 dry-run evidence: `arm-webapp-1781816380-f24c9e5b`, spreadsheet
`log` row 673, three projects passed and zero skipped.

## Historical endpoints

- `AKfycbyAI_cQuCZcca56GdnD5oZuzZkr7Ji2QGEbiBzu9iS-ufV1wLsAJshiEndXyHIy39L6jg`
  was an import-only version-23 restore and is retired.
- Other old ARM deployments listed by `clasp deployments` are historical and
  must not replace the registered production endpoint without a reviewed
  migration.
