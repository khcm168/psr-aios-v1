# Project Agent Contract: psr-aios-v1 Self-Management

## Project Role

`psr-aios-v1` is a WebApp client project and import-health observer. It may
validate ARM endpoint compatibility for its own import flows, but it is not the
owner of shared queue preview or shared deployment mutation.

## Local State Machine

```text
idle
  -> probe_import_endpoint
  -> diagnose
  -> repairable_local_config?
  -> repair_local_runtime
  -> reprobe_import_endpoint
  -> healthy | degraded | blocked
```

### Project Healthy Conditions

- Import endpoint doctor passes.
- Required ARM contract fields match expected compatibility.
- Local runtime and dependency paths are readable.
- No local stale lock prevents the read-only probe.

## Lock Usage

- May hold `local_runtime:psr-aios-v1`.
- Must never request `queue_preview:arm`.
- Must never request `deployment:arm-webapp`.

## Repair Whitelist

### Allowed

- Restart a local non-interactive helper owned by `psr-aios-v1`.
- Clear a stale local lock created by `psr-aios-v1` after TTL expiry.
- Rebuild a local cache or generated snapshot used only by this repo.
- Re-run the import doctor once after a local runtime repair.

### Blocked

- Editing ARM deployment or shared registry.
- Writing into `ARM`, `line_edge_selenium`, or `easyflow`.
- Running the shared queue preview.
- Printing or relocating secrets.

## Failure Classes

- `project_local`
  Local venv, path, cache, or lock issue.
- `shared_config`
  ARM release or contract mismatch.
- `external_dependency`
  Network, VPN, or Google Apps Script access issue.
- `human_required`
  Any needed `.env` or endpoint ownership change.

## Summary Line Format

```text
psr-aios-v1: 🟢 import endpoint OK
psr-aios-v1: 🔴 contract mismatch, local import probe blocked
psr-aios-v1: 🔴 local runtime blocked, repair not allowed
```

## Solo Z13 Operating Note

On a single Z13, `psr-aios-v1` must remain lightweight and read-only during the
nightly health run. It should never claim queue ownership just because it can
reach the same spreadsheet or WebApp.
