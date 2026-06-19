# ARM Shared WebApp Orchestration

Canonical source, deployment registry, and orchestrator live in
`C:\Dev\psr-gas`. This project consumes the shared endpoint for Collection
import. ARM owns the single full remitter queue preview.

Production release `37` was proven on 2026-06-19 by run
`arm-webapp-1781816380-f24c9e5b`; the structured evidence is in production
spreadsheet `log`, row 673. All three registered projects passed:
`psr-aios-v1`, `ARM`, and `line_edge_selenium`.

Run the proof from the canonical checkout:

```powershell
python C:\Dev\psr-gas\tools\arm_webapp_orchestrator.py --dry-run
```

Dry-run does not edit `.env`. It injects `ARM_WEBAPP_CANDIDATE_URL` only into
the doctor process, runs `--check import`, and writes one audit row after the
registered probes finish. Use `--apply` only after a fully successful logged
proof; it can change only the URL variables listed in the canonical registry.

Do not add the remitter preview back to this project's orchestrator probe.
Running it here and again in ARM duplicates a slow Collection/ledger scan and
can create cascading client timeouts.

Bot and programmer rules:

- Never infer the live version from newest Apps Script version; verify the
  version attached to the production deployment ID.
- Never copy, print, or commit `ARM_WEBAPP_TOKEN`.
- Keep the local endpoint snapshot and operational record aligned with the
  proven canonical release.
- A failed proof blocks configuration changes and compatibility claims.
- For rollback, restore the previous deployment version and matching registry,
  then rerun the complete dry-run.
