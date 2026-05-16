# Development Rules

## Folder Rules

- `automations/NN_Name/` is the human-facing launcher layer. Number prefixes define the normal operating order.
- `scripts/` keeps compatibility Python scripts and legacy batch entry points.
- `app/` keeps reusable/tested Python modules.
- `tests/` must cover fragile sheet assumptions before live runs.
- `data/` is generated output. Keep only `.gitkeep` placeholders in git unless a specific artifact is intentionally committed.

## Automation Rules

- Every live automation should print progress steps.
- Every automation that can write to Sheets should support a safe preview path, such as `--dry-run`, `--max-rows`, `--skip-ollama`, or explicit `--writeback`.
- Direct execution should avoid large writebacks by default.
- Batch and command launchers must be repo-relative. Do not hard-code `C:\Users\...` paths.
- Use numbered names such as `10_ARM_Output`, `20_CRM_Refresh`, and `30_N1_Sales_LLM`.

## Sheet Column Rules

- Do not depend on fixed source columns when headers are available.
- Resolve moved sheet columns by visible headers, `Data_Dictionary`, or named constants.
- Fixed cells/ranges are allowed only for intentional layout targets, such as `Collection!C1`, and must have a named constant/env override.
- Before writing, log or print the target sheet/range.

## Git Rules

- Commit by functional slice.
- Do not commit `.env`, service-account files, `.venv`, `.deps`, caches, or generated report outputs.
- Prefer committing tests with the code change that they protect.
