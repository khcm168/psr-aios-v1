# 90 CRM Work Record Keyin

Watches the Google Sheet dropdowns at `V!T1` and `Collection!U1`.

When the value is `work record keyin`, it first claims the cell with a non-trigger `running crm work record keyin ...` value, runs `scripts/crm_work_record_lookup.py`, resets `V!T1` to `none`, and writes start/result rows to the `log` sheet.

The same watcher also accepts `LLM>T` for the local-Ollama edit path. It claims `V!T1`, runs `scripts/v_work_record_polish.py --all --target-column T,U --prompt-row 2 --writeback`, resets `V!T1` to `none`, and logs the trigger result.

The same desktop watcher also accepts `AI keyin`, `mesh operation`, and `check out` from `Collection!U1`. It claims `Collection!U1` with a non-trigger running value, runs the matching ARM batch from `C:\Dev\ARM`, and resets `Collection!U1` to `none` only after the ARM batch exits successfully. A failed ARM batch writes a non-trigger failed marker instead of re-running the same value.

## Daily Command

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd
```

Leave the window open. The watcher checks `V!T1` and `Collection!U1` every 15 seconds. After restart, the visible window should print both `V!T1 triggers` and `Collection!U1 triggers`.

## Windows Schedule

The Windows Task Scheduler setup uses a no-pause launcher:

```powershell
automations\90_CRM_Work_Record_Keyin\watch_scheduled.cmd
```

Registered tasks:

| Task | Time | Purpose |
| --- | --- | --- |
| `\PSR AIOS\CRM Work Record Watch` | Daily 06:00 | Start the watcher |
| `\PSR AIOS\CRM Work Record Watch Stop` | Daily 00:00 | Stop the watcher task |

The start task also has an 18-hour execution limit, so a normal 06:00 run is stopped at midnight even if the stop task is missed.

Useful checks:

```powershell
Get-ScheduledTask -TaskPath "\PSR AIOS\" -TaskName "CRM Work Record Watch"
Get-ScheduledTaskInfo -TaskPath "\PSR AIOS\" -TaskName "CRM Work Record Watch"
Start-ScheduledTask -TaskPath "\PSR AIOS\" -TaskName "CRM Work Record Watch"
Stop-ScheduledTask -TaskPath "\PSR AIOS\" -TaskName "CRM Work Record Watch"
```

Scheduled stdout/stderr appends to:

```text
data/crm_work_record_trigger/watch_scheduled.log
```

## Trigger Values

| Cell value | Behavior |
| --- | --- |
| `work record keyin` | Runs CRM work record key-in for today's `V` rows |
| `LLM>T` | Reads all of today's nonblank `V!T` work-record cells, replaces `V!T` from `V!T2`, and writes `V!U` from `V!U2` with local Ollama |
| `none` | Idle/default value |

`Collection!U1` values:

| Cell value | Behavior |
| --- | --- |
| `AI keyin` | Runs `C:\Dev\ARM\automations\run_checked_remittances.bat` |
| `mesh operation` | Runs `C:\Dev\ARM\automations\run_checked_remittances_mesh.bat` |
| `check out` | Runs `C:\Dev\ARM\automations\run_checked_check_remittances.bat` |
| `none` | Idle/default value |

The CRM run uses the current defaults:

- Browser: Edge
- Twinplay layout: visible desktop windows are minimized first, then the worker CLI is restored to the right at normal console zoom and the CRM browser opens on the left at 50% browser zoom
- Worker output streams live in the right CLI and is also saved under `data/crm_work_record_trigger/`.
- Sheet tab: `V`
- Date: today in Asia/Taipei, formatted like `2026/5/29`
- Test record: skipped
- Row process status: written to column `V`, such as `V!V24`
- Local duplicate ledger: `data/crm_work_record_trigger/crm_work_record_ledger.jsonl`

## Useful Options

Check once and exit:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --once
```

Safest proof for an armed trigger. This reads `V!T1` and `Collection!U1`, then prints the intended command without logging, resetting, or opening CRM/ARM:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --probe
```

Dry-run the trigger bridge without opening CRM:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --once --dry-run
```

If `V!T1` is already `work record keyin` or `LLM>T`, or `Collection!U1` is already `AI keyin`, `mesh operation`, or `check out`, dry-run still accepts and consumes the trigger: it claims the cell, resets it to `none`, and writes `started`/`success` rows to `log`; it only skips the underlying CRM/Ollama/ARM subprocess. Use `--probe` when you only want evidence and do not want to clear the pending trigger.

Preview what the `LLM>T` job will edit without consuming `V!T1`:

```powershell
automations\91_V_Work_Record_Polish\preview.cmd --all --target-column T,U --prompt-row 2
```

Replay a specific date:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --date 2026/5/26
```

Limit the CRM run during a proof:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --max-rows 1
```

Restart at row 24 after fixing sheet data:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --once --start-row 24
```

Rows already present in the local ledger are not saved again. They are marked in column `V` like:

```text
2026-07-23 13:37:13 sent (duplicate ledger skipped) - Local ledger already contains this row; CRM save was not repeated.
```

## Logs

The watcher appends operation rows to the `log` sheet:

- `started` when the dropdown trigger is accepted
- `success` when CRM/Ollama/ARM exits with code `0`
- `error` when CRM/Ollama/ARM exits non-zero

Local CRM/Ollama/ARM stdout and stderr are also saved under `data/crm_work_record_trigger/`.
