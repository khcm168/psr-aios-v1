/**
 * ARM WebApp operational record.
 *
 * Apps Script/clasp does not preserve Markdown as a script file, so this JS file
 * is the Apps Script-side recovery note for the Python ARM WebApp integration.
 * Do not store secrets here.
 */
const ARM_WEBAPP_OPERATIONAL_RECORD = Object.freeze({
  verifiedDate: '2026-06-18',
  pythonProjectRoot: 'C:\\Dev\\psr-aios-v1',
  scriptId: '199VYDwi4DHWaITv48vO1mri4i20C9CJ0euOsvEs3dHwUfNrwlBF02t6x',
  deploymentId: 'AKfycbwLNOVxJlC6e18PVZJ-KzzZu63SfadIUnSyfohzybE0RA1hduKZWHW2C0jYDfSe1gTDxA',
  deployedVersion: 37,
  contract: 'ARM Shared WebApp API',
  contractVersion: '2.0.0',
  execUrl: 'https://script.google.com/macros/s/AKfycbwLNOVxJlC6e18PVZJ-KzzZu63SfadIUnSyfohzybE0RA1hduKZWHW2C0jYDfSe1gTDxA/exec',
  envVars: [
    'ARM_WEBAPP_URL',
    'ARM_IMPORT_WEBAPP_URL',
    'ARM_REMMITER_WEBAPP_URL'
  ],
  tokenProperty: 'ARM_WEBAPP_TOKEN',
  webapp: {
    executeAs: 'USER_DEPLOYING',
    access: 'ANYONE_ANONYMOUS'
  },
  actions: {
    importRows: 'POST rows -> updateArmCollectionReceivablesFromRows',
    previewQueue: 'action=previewAiRemitterQueue -> previewAiRemmiterQueueForWebApp_',
    beginDirectRun: 'action=beginAiRemitterDirectRun',
    recordDirectStep: 'action=recordAiRemitterDirectStep',
    releaseDirectRun: 'action=releaseAiRemitterDirectRun',
    mesh: 'action=appendMeshCustomerQueue',
    orchestratorAudit: 'action=recordOrchestratorAudit -> LOG'
  },
  requiredFiles: [
    '61_ARM_WebApp_Endpoint.js',
    '37_collection_AI_Remmiter.js',
    '38_collection_mesh.js',
    'appsscript.json'
  ],
  verifyCommands: [
    'C:\\Dev\\psr-aios-v1\\.venv\\Scripts\\python.exe C:\\Dev\\psr-aios-v1\\scripts\\doctor_arm_webapps.py --check all',
    'C:\\Dev\\psr-aios-v1\\.venv\\Scripts\\python.exe C:\\Dev\\psr-aios-v1\\scripts\\collection_ai_remmiter.py --dry-run --limit 1'
  ]
});

function getArmWebAppOperationalRecord() {
  return ARM_WEBAPP_OPERATIONAL_RECORD;
}
