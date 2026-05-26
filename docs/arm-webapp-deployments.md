# ARM WebApp Deployment Registry

Track Apps Script WebApp deployments here instead of repointing shared URLs from memory.

| Workflow | Env var | Deployment type | Deployment ID | `/exec` URL | Access mode | Purpose | Last verified date |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ARM import | `ARM_IMPORT_WEBAPP_URL` | Web app | `AKfycbxhZ1mGrd1nldtGvxX1Rm8k0ELsFLWHdVkbUML21-HwLbO0Qcay8WNITAl5xuBqrH4STw` | `https://script.google.com/macros/s/AKfycbxhZ1mGrd1nldtGvxX1Rm8k0ELsFLWHdVkbUML21-HwLbO0Qcay8WNITAl5xuBqrH4STw/exec` | `Everyone` | ARM to Collection import health endpoint and row import contract | `2026-05-26` |
| Legacy shared fallback | `ARM_WEBAPP_URL` | Web app | `AKfycbyFFZnxKail_A-zcf-9vKyiG2ktf8etBMJe09Xw_mABdNuyPZTo7vWKz7EP2CzGr2IM-w` | `https://script.google.com/macros/s/AKfycbyFFZnxKail_A-zcf-9vKyiG2ktf8etBMJe09Xw_mABdNuyPZTo7vWKz7EP2CzGr2IM-w/exec` | `Access denied on verification` | Legacy fallback only; do not assign new workflows here | `2026-05-26` |
| AI Remmiter | `ARM_REMMITER_WEBAPP_URL` | Web app | `TBD` | `TBD` | `TBD` | Queue fetch and result writeback contract for `collection_ai_remmiter.py` | `TBD` |

Notes:

- New deployments should be assigned per contract, not by reusing `ARM_WEBAPP_URL`.
- Update this table whenever a deployment is created, repointed, or reverified.
