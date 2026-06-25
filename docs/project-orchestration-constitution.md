# Project Orchestration Constitution

This guide defines how the upper governor thread and the local project threads cooperate. Every agent or bot must review this guide before taking action across governed projects.

The goal is simple: keep projects tidy, traceable, testable, and fixable without creating noisy multi-actor confusion.

## Roles

- **Accountable user**: the only person who decides scope, merge, deploy, and live external actions.
- **Governor**: coordinates across projects, sets order, checks evidence, identifies drift, and hands work to the right project.
- **Local project agent**: implements, tests, documents, and proves behavior inside its own repo.
- **Live systems**: Google Sheets, Apps Script WebApp, CRM, LINE, browser automation, scheduled jobs, and external APIs. These require explicit care.

## Article 1 — Governor decides direction and order

The governor owns cross-project perspective, not every local implementation detail.

Governor responsibilities:

- decide which project should move first;
- identify whether a change is cross-project governance, local implementation, or live operation;
- review PR readiness and merge order;
- detect inconsistent config, endpoint drift, credential gaps, dirty worktrees, and missing documentation;
- write handoff notices when work should return to a local project.

The governor must not silently convert a coordination task into broad repo development. If it implements directly, it must explain why and leave a handoff trail.

## Article 2 — Local projects own implementation and proof

Each repo owns its own code, tests, runbooks, launchers, and live workflow proof.

Local project responsibilities:

- implement code changes in a focused branch;
- run repo-specific tests and compile/static checks;
- maintain local README, runbook, and `AGENTS.md`;
- perform dry-run or limited proof before live operation;
- keep generated logs, credentials, tokens, and scratch files out of git.

Live proof belongs to the local project unless the accountable user explicitly asks the governor to execute it.

## Article 3 — Governor intervenes only when useful

Governor intervention is appropriate for:

- emergency stabilization;
- cross-project orchestration changes;
- endpoint/version/config drift;
- PR dependency ordering;
- repeated local failure where global context is needed;
- migration of a proven pattern from one project to another.

Governor intervention is not appropriate for routine local feature work when a respective project can own it cleanly.

When the governor intervenes, it must still use normal discipline:

- branch;
- commit;
- tests/proof;
- PR;
- merge record;
- handoff notice;
- remaining risk.

## Article 4 — Every cross-layer transfer needs a handoff notice

When work moves between governor and local project, the handoff notice must include:

- repo and local path;
- branch, PR URL, and merge commit if available;
- files changed;
- tests or proof already performed;
- what was not done;
- next owner;
- live-action warning;
- suggested next command or checklist;
- rollback or recovery notes when relevant.

Use this rule even when the work feels small. Small undocumented transfers become tomorrow's confusion.

## Article 5 — Dirty worktrees are not the source of truth

Remote merged main/master is the governance truth. A local dirty worktree is a workbench.

Before syncing or continuing local work:

- inspect `git status --short --branch`;
- compare dirty files with merged remote state;
- identify unrelated local changes;
- do not reset, checkout, or overwrite user work unless explicitly authorized;
- do not assume untracked logs or scratch files belong in a PR.

If a local worktree is dirty after remote merge, create a clear cleanup plan instead of forcing a pull/reset.

## Required pre-action review

Before acting, every agent must answer these questions internally and mention the important ones in its report:

1. Which role am I playing: governor or local project agent?
2. Which repo owns the next change?
3. Is this read-only, code implementation, merge, deploy, or live external action?
4. Is the worktree clean enough to proceed safely?
5. What evidence will prove success?
6. What should not be touched?
7. Who owns the next step after this turn?

If the answer changes during work, stop and reclassify before continuing.

## Branch and PR discipline

Use one functional slice per branch. Good branches are small enough to explain in one breath.

Required merge evidence:

- branch name;
- commit hash;
- PR URL;
- tests or dry-run proof;
- known exclusions;
- rollback path or safe next step.

Do not merge unrelated local changes just because they are present.

## Live-action discipline

Live actions include, but are not limited to:

- writing Google Sheets;
- deploying Apps Script;
- invoking WebApp production endpoints;
- sending LINE messages;
- operating CRM browser automation;
- changing scheduled jobs;
- altering credentials or environment variables.

Live actions require explicit accountable-user scope. A dry-run that still reads/resets a trigger cell or appends a log row should be treated as live-adjacent and described clearly before execution.

## Handoff notice template

```text
Please take over this work in the respective project.

Repo:
Local path:
Owner now:
Governor context:
Merged PR / branch / commit:

What changed:
- ...

Validation already done:
- ...

Not done:
- ...

Live-action warning:
- ...

Recommended next steps:
1. ...
2. ...
3. ...

Do not:
- ...
```

## Working agreement

The governor is the control tower. Local projects are the hangars and maintenance crews. The accountable user decides what flies.

Keep the system calm: fewer actors, clearer ownership, smaller PRs, stronger evidence.
