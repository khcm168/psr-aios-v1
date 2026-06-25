# 90 CRM Work Record Keyin

Watches the Google Sheet dropdown at `V!T1`. When the value is `work record keyin`, it runs `scripts/crm_work_record_lookup.py`, resets `V!T1` to `none`, and writes start/result rows to the `log` sheet.

## Daily Command

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd
```

Leave the window open. The watcher checks `V!T1` every 15 seconds.

## Trigger Values

| Cell value | Behavior |
| --- | --- |
| `work record keyin` | Runs CRM work record key-in for today's `V` rows |
| `none` | Idle/default value |

The CRM run uses the current defaults:

- Browser: Edge
- Sheet tab: `V`
- Date: today in Asia/Taipei, formatted like `2026/5/29`
- Test record: skipped

## Useful Options

Check once and exit:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --once
```

Dry-run the trigger bridge without opening CRM:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --once --dry-run
```

If `V!T1` is already `work record keyin`, dry-run still accepts the trigger, resets `V!T1` to `none`, and writes `started`/`success` rows to `log`; it only skips the CRM browser save.

Replay a specific date:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --date 2026/5/26
```

Limit the CRM run during a proof:

```powershell
automations\90_CRM_Work_Record_Keyin\watch.cmd --max-rows 1
```

## Logs

The watcher appends operation rows to the `log` sheet:

- `started` when the dropdown trigger is accepted
- `success` when CRM exits with code `0`
- `error` when CRM exits non-zero

Local CRM stdout/stderr is also saved under `data/crm_work_record_trigger/`.
