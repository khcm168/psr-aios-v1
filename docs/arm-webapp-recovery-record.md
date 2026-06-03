# ARM WebApp Recovery Record

This file records the known-good state after the OneDrive-to-C:\Dev move caused stale .env and stale WebApp deployment IDs.

## Good Endpoint

`	ext
https://script.google.com/macros/s/AKfycbwLNOVxJlC6e18PVZJ-KzzZu63SfadIUnSyfohzybE0RA1hduKZWHW2C0jYDfSe1gTDxA/exec
`

This is deployment $deploymentId, version 27, in Apps Script project $scriptId.

The same URL is intentionally used by:

`	ext
ARM_WEBAPP_URL
ARM_IMPORT_WEBAPP_URL
ARM_REMMITER_WEBAPP_URL
`

## Why One URL Works

61_ARM_WebApp_Endpoint now handles both workflows:

- Plain import POST with ows -> updateArmCollectionReceivablesFromRows
- ction=getAiRemmiterQueue -> getCollectionAiRemmiterQueue
- ction=recordAiRemmiterResults -> ecordCollectionAiRemmiterResults

This preserves rm_export_to_collection.py while restoring collection_ai_remmiter.py.

## Verification Commands

`powershell
C:\Dev\psr-aios-v1\.venv\Scripts\python.exe C:\Dev\psr-aios-v1\scripts\doctor_arm_webapps.py --check all
C:\Dev\psr-aios-v1\.venv\Scripts\python.exe C:\Dev\psr-aios-v1\scripts\collection_ai_remmiter.py --dry-run --limit 1
`

Expected:

`	ext
doctor: passed=2 failed=0
remitter dry-run: Queue valid rows > 0, invalid checked rows: 0
`

## Files That Must Stay Together

Python repo C:\Dev\psr-aios-v1:

`	ext
.env
apps_script/61_ARM_WebApp_Endpoint.gs
apps_script/37_collection_AI_Remmiter.js
scripts/collection_ai_remmiter.py
scripts/arm_export_to_collection.py
scripts/doctor_arm_webapps.py
`

Apps Script repo psr-gas:

`	ext
appsscript.json
00_ARM_WebApp_Operational_Record.js
61_ARM_WebApp_Endpoint.js
37_collection_AI_Remmiter.js
`

Secrets are intentionally excluded from git. The important non-secret deployment facts are stored here and in the Apps Script JS record file.