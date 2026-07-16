# Agent Objectives and Loop

Use this guide when acting as an automation agent in this repo. The goal is to keep work useful, auditable, and safe around live Google Sheets data.

## Good Vibe Code Practice

Work like a careful teammate, not a frantic fixer. Keep the repo calm, readable, and recoverable.

- Start by observing: read the relevant docs, check `git status --short`, and understand what is already dirty before changing files.
- Keep each change small enough to explain in one breath: one workflow, one behavior, one cleanup theme.
- Prefer boring code that survives tomorrow: repo-relative paths, named constants, header-based lookup, and deterministic output.
- Protect the operator's trust: never hide credentials in code, never commit generated artifacts, and never run live writes before a dry run or small-scope proof.
- Make cleanup visible: remove disposable caches and invalid scratch files, but do not delete local outputs, env files, or user work unless that is the explicit task.
- Close every loop with evidence: tests run, commands used, files touched, and any risk that remains.
- Leave a handhold for the next agent: docs, launchers, and failure messages should help a tired human recover quickly.

## Objectives

1. Protect live business data.
   - Prefer preview, dry-run, or small-row execution before any live write.
   - Print or log the exact target sheet, tab, range, and row count before writing.
   - Treat direct full writeback as the last step, not the first experiment.

2. Preserve sheet resilience.
   - Resolve source columns by visible headers, `Data_Dictionary`, or named constants.
   - Avoid fixed column letters unless the target is an intentional layout cell.
   - Add tests for moved columns, renamed headers, sparse rows, and unusual tab shapes.

3. Keep workflows operator-friendly.
   - Put daily launch paths in `automations/NN_Name/`.
   - Keep `.cmd` launchers repo-relative and compatible with `.venv\Scripts\python.exe`.
   - Document the safe first command, live command, inputs, outputs, and rollback notes.

4. Make generated output traceable.
   - Write local report artifacts under `data/` unless a workflow explicitly needs Sheets output.
   - Log meaningful operation rows, including result links when artifacts are produced.
   - Keep generated artifacts, credentials, tokens, caches, and local scratch files out of git.

5. Change by functional slice.
   - Keep edits focused on the workflow being improved.
   - Prefer existing modules, launch conventions, and test style over new abstractions.
   - Commit tests with the behavior they protect.

6. Respect ARM WebApp release ownership.
   - Only canonical `C:\Dev\psr-gas` may edit `arm_webapp_registry.json`, bump
     the canonical `61_ARM_WebApp_Endpoint.js`, or deploy the shared ARM
     WebApp. This repo may mirror reviewed Apps Script snapshots after a
     `psr-gas` release, but must not originate release claims.
   - Client checks must honor orchestrator-provided registry values such as
     `ARM_WEBAPP_EXPECTED_RELEASE_VERSION`; do not accept a newer or older
     WebApp release just because the endpoint is reachable.
   - A changed shared endpoint is not complete until the `psr-gas` release
     workflow proves all registered projects and records audit evidence.
   - During orchestration, `psr-aios-v1` runs import health only; `ARM` owns
     the full queue preview.

## Working Loop

1. Sweep the floor.
   - Run `git status --short --branch` before edits.
   - Notice untracked source, ignored artifacts, generated files, and accidental duplicates.
   - Remove only safe disposable clutter such as `__pycache__/` and `*.pyc`; leave `.env`, `.venv/`, `.deps/`, and report outputs alone unless cleanup of those files is explicitly requested.

2. Orient.
   - Read `README.md`, `docs/workflow-reference.md`, and the relevant `automations/NN_Name/README.md`.
   - Avoid disturbing unrelated user changes.
   - Identify whether the task touches local files only, live Sheets, Apps Script, or external services.

3. Map the workflow.
   - Find the Python entry point, launcher, env vars, source tabs, destination tabs, and write ranges.
   - Confirm the safest first command: dry run, preview, `--max-rows`, `--skip-ollama`, or explicit no-write mode.
   - Note fragile assumptions such as headers, adjacent output columns, status cells, workbook titles, and date filters.

4. Plan the smallest safe change.
   - Prefer a narrow fix with focused tests.
   - Add or update docs only where the operator will actually look during a run.
   - For Sheet writes, keep validation close to the write boundary.

5. Implement.
   - Reuse existing helpers in `app/` and compatibility patterns in `scripts/`.
   - Keep path handling repo-relative.
   - Make output deterministic enough to test, especially around dates and header lookup.

6. Verify locally.
   - Run focused tests first.
   - Run the standard checks when the change is broader:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m compileall app scripts tests
```

7. Verify workflow behavior.
   - Run the safe command first and inspect printed target ranges, row counts, and artifact paths.
   - If a live run is required, run the smallest useful live sample before the full job.
   - Check operation logs or produced files after the run.

8. Pre-sync hygiene.
   - Re-run `git status --short --branch` and review `git diff --stat`.
   - Confirm no secrets, tokens, local report packs, caches, or broken launcher copies are about to be committed.
   - If GitHub sync is needed, confirm the remote exists and the branch name is intentional before push.

9. Close the loop.
   - Summarize what changed, what was verified, and any remaining risk.
   - Name exact files, commands, and outputs so the next operator can reproduce the result.
   - Leave the repo cleaner than you found it, without reverting unrelated work.

## Live Write Gate

Before any command that writes to Sheets or Apps Script, confirm all of the following:

- The destination spreadsheet ID and worksheet/tab are known.
- The command has already been run in dry-run, preview, or small-scope mode when available.
- The code prints or logs target ranges before writing.
- Header-based lookup or `Data_Dictionary` mapping has been used wherever possible.
- The intended write scope is limited to the workflow being operated.

If any item is missing, pause and add the missing guardrail before running live.

<!-- PRO-AI GOVERNANCE START -->
## Shared Multi-Project Agent Governance

This repository participates in a four-project autonomous health system on a
single Lenovo Z13 operated by one programmer with Codex capability, internet,
and VPN access.

### Required Role Separation

- `monitor` agents run read-only probes only.
- `diagnose` agents classify failures and choose escalation scope.
- `repair` agents may run only allowlisted, idempotent repairs.
- `summary` agents generate concise Traditional Chinese reports.
- `delivery` agents send prepared artifacts only and must not reinterpret
  health.

### Shared Resource Rules

- Shared mutable resources require an explicit lease.
- `ARM` is the only queue-preview owner.
- `line_edge_selenium` is the only LINE delivery executor.
- Observer projects must remain read-only during orchestration.
- No agent may copy secrets, token files, or service-account JSON between
  repositories.

### Autonomy Rules

- Degrade on uncertainty. Do not silently skip reporting.
- Shared config mismatch must be reported as `CONFIG FAIL`, not masked.
- Delivery failure must not erase health evidence.
- Any deployment, registry, or `.env` mutation requires human escalation unless
  an explicit local policy says otherwise.

### Shared Summary Contract

Nightly summary must include:

1. `???亙?獢摨瑕??YYYY-MM-DD?
2. overall `?` or `?`
3. one line for each of the four projects
4. shared release / audit / worker status when known
5. one short next-action line

## Project Agent Policy: psr-aios-v1

### Role

`psr-aios-v1` is a WebApp client and import-health observer. It may validate
its own ARM endpoint compatibility but must not claim shared queue ownership.

### Allowed Automatic Repairs

- restart local non-interactive helpers owned by `psr-aios-v1`
- clear expired local locks created by this project
- rebuild deterministic local cache or snapshot artifacts
- re-run the import endpoint doctor once after a local repair

### Forbidden Automatic Repairs

- mutate ARM deployment or shared registry
- write into another repository
- run shared queue preview
- print, relocate, or copy secrets

### Required State Outcomes

- `healthy` when import compatibility passes
- `degraded` when shared config is bad but local evidence is still readable
- `blocked` when a needed action exceeds local authority
<!-- PRO-AI GOVERNANCE END -->

