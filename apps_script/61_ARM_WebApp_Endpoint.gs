const ARM_WEBAPP_CFG = {
  tokenPropertyName: 'ARM_WEBAPP_TOKEN',
  contractName: 'ARM Shared WebApp API',
  contractVersion: '2.0.0',
  releaseVersion: 37,
  deploymentId: 'AKfycbwLNOVxJlC6e18PVZJ-KzzZu63SfadIUnSyfohzybE0RA1hduKZWHW2C0jYDfSe1gTDxA',
  spreadsheetId: '1eTnZppbhu7fpwdFTrnFoQmxchylsZus0Sw4j1t61Zzo',
  sheetName: 'Collection',
  headerRow: 2,
  startRow: 3,
  startCol: 2, // B
  statusCol: 9, // I
  sourceCols: 7,
  maxRows: 5000,
  logSheetName: 'LOG'
};

function doGet() {
  return createArmWebAppJsonResponse_({
    ok: true,
    message: 'ARM Collection import endpoint is available.',
    contract: ARM_WEBAPP_CFG.contractName,
    contractVersion: ARM_WEBAPP_CFG.contractVersion,
    releaseVersion: ARM_WEBAPP_CFG.releaseVersion,
    deploymentId: ARM_WEBAPP_CFG.deploymentId,
    capabilities: [
      'collectionImport',
      'previewAiRemitterQueue',
      'beginAiRemitterDirectRun',
      'recordAiRemitterDirectStep',
      'releaseAiRemitterDirectRun',
      'getAiRemitterDirectRunLock',
      'clearAiRemitterDirectRunLock',
      'appendMeshCustomerQueue',
      'recordOrchestratorAudit'
    ]
  });
}

function doPost(e) {
  try {
    const payload = parseArmWebAppPayload_(e);
    assertArmWebAppToken_(payload.token);

    if (payload.action === 'previewAiRemitterQueue') {
      return createArmWebAppJsonResponse_({
        ok: true,
        result: previewAiRemmiterQueueForWebApp_()
      });
    }

    if (payload.action === 'beginAiRemitterDirectRun') {
      return createArmWebAppJsonResponse_({
        ok: true,
        result: beginCollectionAiRemmiterDirectRun_(payload.workerId)
      });
    }

    if (payload.action === 'recordAiRemitterDirectStep') {
      return createArmWebAppJsonResponse_({
        ok: true,
        result: recordCollectionAiRemmiterDirectStep_(
          payload.runId,
          payload.workerId,
          payload.step
        )
      });
    }

    if (payload.action === 'releaseAiRemitterDirectRun') {
      return createArmWebAppJsonResponse_({
        ok: true,
        result: releaseCollectionAiRemmiterDirectRun_(
          payload.runId,
          payload.workerId,
          payload.summary
        )
      });
    }

    if (payload.action === 'getAiRemitterDirectRunLock') {
      return createArmWebAppJsonResponse_({
        ok: true,
        result: getCollectionAiRemmiterDirectRunLock_()
      });
    }

    if (payload.action === 'clearAiRemitterDirectRunLock') {
      return createArmWebAppJsonResponse_({
        ok: true,
        result: clearCollectionAiRemmiterDirectRunLock_(payload.confirmation)
      });
    }

    if (payload.action === 'appendMeshCustomerQueue') {
      return createArmWebAppJsonResponse_({
        ok: true,
        result: appendCollectionMeshCustomerQueue_(payload.steps, payload.runId)
      });
    }

    if (payload.action === 'recordOrchestratorAudit') {
      return createArmWebAppJsonResponse_({
        ok: true,
        result: recordArmWebAppOrchestratorAudit_(payload.audit)
      });
    }

    if (payload.action === 'g2PrintDateWindow') {
      const result = rebuildG2PrintForDateWindow_(payload.startDate, payload.endDate);
      return createArmWebAppJsonResponse_({
        ok: true,
        message: 'G receipt print sheet rebuilt for requested date window.',
        result: result
      });
    }

    const rows = validateArmWebAppRows_(payload.rows);
    const result = updateArmCollectionReceivablesFromRows(rows);

    return createArmWebAppJsonResponse_({
      ok: true,
      message: 'ARM rows imported into Collection.',
      result: result
    });
  } catch (err) {
    return createArmWebAppJsonResponse_({
      ok: false,
      error: String(err && err.message ? err.message : err)
    });
  }
}

function updateArmCollectionReceivablesFromRows(rows) {
  const cfg = ARM_WEBAPP_CFG;
  const ss = getArmWebAppSpreadsheet_();
  const sheet = ss.getSheetByName(cfg.sheetName);
  if (!sheet) throw new Error('Missing sheet: ' + cfg.sheetName);

  const normalizedRows = validateArmWebAppRows_(rows);
  const previousLastRow = sheet.getLastRow();
  const previousRowCount = Math.max(previousLastRow - cfg.startRow + 1, 0);
  const previousValues = previousRowCount
    ? sheet.getRange(cfg.startRow, cfg.startCol, previousRowCount, cfg.sourceCols + 1).getValues()
    : [];
  const statusByKey = buildArmCollectionStatusIndex_(previousValues);
  const statuses = normalizedRows.map(function(row) {
    return [statusByKey[getArmCollectionRowKey_(row)] || ''];
  });
  const clearRows = Math.max(previousRowCount, normalizedRows.length, 1);

  sheet.getRange(cfg.startRow, cfg.startCol, clearRows, cfg.sourceCols).clearContent();
  sheet.getRange(cfg.startRow, cfg.statusCol, clearRows, 1).clearContent();

  if (normalizedRows.length) {
    sheet.getRange(cfg.startRow, cfg.startCol, normalizedRows.length, cfg.sourceCols).setValues(normalizedRows);
    sheet.getRange(cfg.startRow, cfg.statusCol, statuses.length, 1).setValues(statuses);
  }

  if (typeof applyCollectionStatusSyncStatusValidation_ === 'function') {
    applyCollectionStatusSyncStatusValidation_(sheet);
  }
  if (typeof ensureCollectionAiRemmiterStatusOptions_ === 'function') {
    ensureCollectionAiRemmiterStatusOptions_(sheet);
  }

  const preservedStatusCount = statuses.filter(function(row) {
    return toArmWebAppText_(row[0]);
  }).length;

  appendArmWebAppLog_({
    importedRows: normalizedRows.length,
    previousRows: previousRowCount,
    preservedStatusCount: preservedStatusCount,
    firstKey: normalizedRows.length ? getArmCollectionRowKey_(normalizedRows[0]) : ''
  });

  return {
    importedRows: normalizedRows.length,
    previousRows: previousRowCount,
    preservedStatusCount: preservedStatusCount,
    clearedRows: clearRows
  };
}

function rotateArmWebAppToken() {
  const token = Utilities.getUuid() + '-' + Utilities.getUuid();
  PropertiesService.getScriptProperties().setProperty(ARM_WEBAPP_CFG.tokenPropertyName, token);
  Logger.log('New ARM_WEBAPP_TOKEN: ' + token);
  return token;
}

function authorizeArmWebAppSpreadsheetAccess() {
  const ss = getArmWebAppSpreadsheet_();
  return {
    ok: true,
    spreadsheetName: ss.getName(),
    collectionSheetFound: Boolean(ss.getSheetByName(ARM_WEBAPP_CFG.sheetName))
  };
}

function parseArmWebAppPayload_(e) {
  if (!e || !e.postData || !e.postData.contents) {
    throw new Error('Missing POST body.');
  }
  return JSON.parse(e.postData.contents || '{}');
}

function assertArmWebAppToken_(actualToken) {
  const expectedToken = PropertiesService
    .getScriptProperties()
    .getProperty(ARM_WEBAPP_CFG.tokenPropertyName);

  if (!expectedToken) {
    throw new Error('Missing Script Property: ' + ARM_WEBAPP_CFG.tokenPropertyName);
  }

  if (!actualToken || actualToken !== expectedToken) {
    throw new Error('Unauthorized: invalid token.');
  }
}

function validateArmWebAppRows_(rows) {
  const cfg = ARM_WEBAPP_CFG;
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error('payload.rows must be a non-empty 2D array.');
  }
  if (rows.length > cfg.maxRows) {
    throw new Error('Too many rows: ' + rows.length);
  }

  return rows.map(function(row, i) {
    if (!Array.isArray(row) || row.length !== cfg.sourceCols) {
      throw new Error('Invalid row at index ' + i + '. Expected exactly 7 columns.');
    }
    return row.map(function(value) {
      return toArmWebAppText_(value);
    });
  });
}

function buildArmCollectionStatusIndex_(previousValues) {
  const index = {};
  previousValues.forEach(function(row) {
    const sourceRow = row.slice(0, ARM_WEBAPP_CFG.sourceCols);
    const status = toArmWebAppText_(row[ARM_WEBAPP_CFG.sourceCols]);
    const key = getArmCollectionRowKey_(sourceRow);
    if (key && status && !index[key]) index[key] = status;
  });
  return index;
}

function getArmCollectionRowKey_(row) {
  return toArmWebAppText_(row[3]);
}

function appendArmWebAppLog_(info) {
  const ss = getArmWebAppSpreadsheet_();
  let logSheet = ss.getSheetByName(ARM_WEBAPP_CFG.logSheetName);
  if (!logSheet) logSheet = ss.insertSheet(ARM_WEBAPP_CFG.logSheetName);

  if (logSheet.getLastRow() === 0) {
    logSheet.appendRow([
      'DateTime',
      'Process Name',
      'Purpose',
      'Affected Sheets',
      'Affected Columns',
      'Key Variables',
      'Maintenance Notes'
    ]);
  }

  logSheet.appendRow([
    new Date(),
    'ARM WebApp Import',
    'Import ARM Excel rows posted by local Python automation',
    ARM_WEBAPP_CFG.sheetName + ', ' + ARM_WEBAPP_CFG.logSheetName,
    'Collection!B:H, Collection!I:I',
    'importedRows=' +
      info.importedRows +
      ', previousRows=' +
      info.previousRows +
      ', preservedStatusCount=' +
      info.preservedStatusCount +
      ', firstKey=' +
      info.firstKey,
    'Python performs ARM browser export; Apps Script validates and writes Collection B:H, preserving I status by closing number. Y:AF is not modified.'
  ]);
}

function getArmWebAppSpreadsheet_() {
  return SpreadsheetApp.openById(ARM_WEBAPP_CFG.spreadsheetId);
}

function recordArmWebAppOrchestratorAudit_(audit) {
  if (!audit || typeof audit !== 'object' || Array.isArray(audit)) {
    throw new Error('audit must be an object.');
  }
  const runId = toArmWebAppText_(audit.runId);
  const mode = toArmWebAppText_(audit.mode);
  const status = toArmWebAppText_(audit.status);
  if (!runId || !/^[A-Za-z0-9._-]{1,100}$/.test(runId)) {
    throw new Error('audit.runId is invalid.');
  }
  if (mode !== 'dry-run' && mode !== 'apply') {
    throw new Error('audit.mode must be dry-run or apply.');
  }
  if (status !== 'passed' && status !== 'failed') {
    throw new Error('audit.status must be passed or failed.');
  }
  const projects = Array.isArray(audit.projects) ? audit.projects.slice(0, 20) : [];
  const passed = projects.filter(function(project) {
    return project && project.status === 'passed';
  }).length;
  const failed = projects.length - passed;
  const aliases = projects.map(function(project) {
    return toArmWebAppText_(project && project.name) + '=' +
      toArmWebAppText_(project && project.status);
  }).join(' | ');
  const note = JSON.stringify({
    runId: runId,
    status: status,
    contract: toArmWebAppText_(audit.contract),
    contractVersion: toArmWebAppText_(audit.contractVersion),
    releaseVersion: Number(audit.releaseVersion) || 0,
    deploymentId: toArmWebAppText_(audit.deploymentId),
    durationSeconds: Number(audit.durationSeconds) || 0,
    projects: projects
  }).slice(0, 45000);

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const sheet = getArmWebAppSpreadsheet_();
    let logSheet = sheet.getSheetByName(ARM_WEBAPP_CFG.logSheetName);
    if (!logSheet) logSheet = sheet.insertSheet(ARM_WEBAPP_CFG.logSheetName);
    logSheet.appendRow([
      new Date(),
      'ARM WebApp Orchestrator ' + mode,
      ARM_WEBAPP_CFG.sheetName,
      '',
      '',
      projects.length,
      passed,
      failed,
      'release=' + ARM_WEBAPP_CFG.releaseVersion,
      mode,
      aliases,
      note
    ]);
    return {
      runId: runId,
      logSheet: ARM_WEBAPP_CFG.logSheetName,
      logRow: logSheet.getLastRow(),
      status: status
    };
  } finally {
    lock.releaseLock();
  }
}

function createArmWebAppJsonResponse_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}

function toArmWebAppText_(value) {
  return value == null ? '' : String(value).trim();
}

