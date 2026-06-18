# ARM WebApp Recovery Record

The known-good production state is Apps Script deployment
`AKfycbwLNOVxJlC6e18PVZJ-KzzZu63SfadIUnSyfohzybE0RA1hduKZWHW2C0jYDfSe1gTDxA`,
version `36`, in script project
`199VYDwi4DHWaITv48vO1mri4i20C9CJ0euOsvEs3dHwUfNrwlBF02t6x`.

The same `/exec` URL is intentionally used by `psr-aios-v1` for Collection
import and by `ARM` for direct-run remittance. The endpoint declares its
contract, release, deployment ID, and capabilities through `doGet`.

## Recovery sequence

1. In `C:\Dev\psr-gas`, run `npx.cmd clasp deployments` and
   `npx.cmd clasp versions`.
2. Run `python tools\arm_webapp_orchestrator.py` to compare the live endpoint
   and all registered client URLs.
3. If the live endpoint passes but local URLs drifted, rerun with `--apply`.
4. In `C:\Dev\psr-aios-v1`, run
   `.\.venv\Scripts\python.exe scripts\doctor_arm_webapps.py --check all`.
5. In `C:\Dev\ARM`, run `python scripts\webapp_health.py` and a queue preview
   before any direct remittance.

Never copy or commit `ARM_WEBAPP_TOKEN`. If the endpoint targets another
spreadsheet, create and register a separate deployment instead of repurposing
this production deployment.
