# Project Practice

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
