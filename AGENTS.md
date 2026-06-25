# Project Practice

## Pre-action constitution

Before changing code, running live workflows, opening PRs, merging, deploying,
or touching external systems, read
`docs/project-orchestration-constitution.md`.

Classify the task before acting:

- governor-level coordination;
- local project implementation;
- live action requiring the accountable user's explicit decision;
- dirty-worktree triage where unrelated user work may be present.

Keep one owner per repo/task, one functional slice per branch/PR, and record
evidence before handing work off.

## ARM Shared WebApp orchestration

Before changing ARM WebApp URLs, deployment assumptions, spreadsheet IDs,
credential-path configuration, or ARM automation, read
`docs/arm-webapp-orchestration.md`.

- `psr-aios-v1` owns the import-health probe only.
- ARM alone owns the full queue preview.
- `line_edge_selenium` and `easyflow` are read-only observers.
- Never copy another project's `.env`, commit credential JSON, print tokens, or
  enable interactive authorization inside an orchestration probe.
- Do not claim compatibility or apply URL changes unless the complete logged
  orchestrator dry-run passes and its spreadsheet row is verified.
