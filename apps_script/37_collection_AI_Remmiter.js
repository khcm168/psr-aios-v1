const COLLECTION_AI_REMMITER_CFG = {
  spreadsheetId: '1eTnZppbhu7fpwdFTrnFoQmxchylsZus0Sw4j1t61Zzo',
  sheetName: 'Collection',
  headerRow: 2,
  startRow: 3,
  leftClosingNoCol: 5, // E
  leftStatusCol: 9, // I
  invoiceNoCol: 16, // P
  closingNoCol: 17, // Q
  unpaidCol: 19, // S
  commentCol: 20, // T
  checkboxCol: 21, // U
  customerIdCol: 13, // M
  customerNameCol: 14, // N
  archiveStatusCol: 32, // AF
  maxRows: 5000,
  closingNoPattern: /^61\d{2}-\d{10}$/,
  receiptNoPattern: /^63\d{2}-\d{10}$/,
  cashStatus: '已收款(現金/支票)',
  codStatus: '已折讓',
  ledgerSheetName: 'ARM_Remitter_Ledger',
  logSheetName: 'LOG',
  processName: 'Collection AI Remitter Direct Run',
  directRunProperty: 'ARM_REMITTER_DIRECT_RUN_LOCK'
};

function buildCollectionAiRemmiterMenu_(ui) {
  ui.createMenu('AI Remitter')
    .addItem('Prepare checkboxes and statuses', 'setupCollectionAiRemmiterCheckboxes')
    .addItem('Preview checked groups', 'previewCollectionAiRemmiterQueue')
    .addSeparator()
    .addItem('Show direct-run lock', 'showCollectionAiRemmiterDirectRunLock')
    .addItem('Clear reviewed direct-run lock', 'clearCollectionAiRemmiterDirectRunLockFromMenu')
    .addToUi();
}

function setupCollectionAiRemmiterCheckboxes() {
  const sheet = getCollectionAiRemmiterSheet_();
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const lastRow = Math.max(sheet.getLastRow(), cfg.startRow);
  const endRow = Math.min(Math.max(sheet.getMaxRows(), lastRow), cfg.maxRows);
  const numRows = Math.max(endRow - cfg.startRow + 1, 1);
  const range = sheet.getRange(cfg.startRow, cfg.checkboxCol, numRows, 1);
  const values = range.getValues().map(function(row) {
    return [isCollectionAiRemmiterChecked_(row[0])];
  });
  applyCollectionAiRemmiterCheckboxValidation_(range);
  range.setValues(values);
  ensureCollectionAiRemmiterStatusOptions_(sheet);
  return {
    checkboxRange: cfg.sheetName + '!U' + cfg.startRow + ':U' + endRow,
    checkboxRows: numRows
  };
}

function previewCollectionAiRemmiterQueue() {
  const result = previewAiRemmiterQueueForWebApp_();
  const message = [
    'Executable steps: ' + result.executableStepCount,
    'Skipped steps: ' + result.skippedStepCount,
    'Invalid checked rows: ' + result.invalidCheckedRows.length,
    '',
    'Run the desktop "Execute Checked ARM Remittances" shortcut after review.'
  ].join('\n');
  showCollectionAiRemmiterAlert_(message);
  return result;
}

function previewAiRemmiterQueueForWebApp_() {
  return buildCollectionAiRemmiterQueue_(getCollectionAiRemmiterSheet_());
}

function buildCollectionAiRemmiterQueue_(sheet) {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const lastRow = Math.min(Math.max(sheet.getLastRow(), cfg.startRow), cfg.maxRows);
  const numRows = Math.max(lastRow - cfg.startRow + 1, 0);
  if (!numRows) {
    return emptyCollectionAiRemmiterQueue_();
  }

  const invoiceValues = sheet.getRange(cfg.startRow, cfg.invoiceNoCol, numRows, 1).getDisplayValues();
  const closingValues = sheet.getRange(cfg.startRow, cfg.closingNoCol, numRows, 1).getDisplayValues();
  const unpaidValues = sheet.getRange(cfg.startRow, cfg.unpaidCol, numRows, 1).getDisplayValues();
  const commentValues = sheet.getRange(cfg.startRow, cfg.commentCol, numRows, 1).getDisplayValues();
  const checkboxValues = sheet.getRange(cfg.startRow, cfg.checkboxCol, numRows, 1).getValues();
  const customerIdValues = sheet.getRange(cfg.startRow, cfg.customerIdCol, numRows, 1).getDisplayValues();
  const customerNameValues = sheet.getRange(cfg.startRow, cfg.customerNameCol, numRows, 1).getDisplayValues();
  const statusIndex = buildCollectionAiRemmiterIStatusIndex_(sheet);
  const ledgerIndex = readCollectionAiRemmiterLedgerIndex_(ensureCollectionAiRemmiterLedger_());
  const invalidCheckedRows = [];
  const records = [];

  for (let index = 0; index < numRows; index++) {
    if (!isCollectionAiRemmiterChecked_(checkboxValues[index][0])) continue;
    const rowNumber = cfg.startRow + index;
    const invoiceNo = toCollectionAiRemmiterText_(invoiceValues[index][0]);
    const closingNo = toCollectionAiRemmiterText_(closingValues[index][0]);
    const unpaidText = toCollectionAiRemmiterText_(unpaidValues[index][0]);
    const unpaidAmount = toCollectionAiRemmiterNumber_(unpaidText);
    const prefix = closingNo.slice(0, 4);
    let reason = '';
    if (!invoiceNo) reason = 'Blank Collection!P invoice number.';
    else if (!cfg.closingNoPattern.test(closingNo)) reason = 'Invalid Collection!Q closing number.';
    else if (!unpaidAmount) reason = 'Collection!S amount is blank, invalid, or zero.';
    else if (prefix === '6101' && !(unpaidAmount > 0)) reason = '6101 amount must be positive.';
    else if (prefix === '6105' && !(unpaidAmount < 0)) reason = '6105 amount must be negative.';
    else if (prefix !== '6101' && prefix !== '6105') reason = 'Only 6101 and 6105 are supported.';
    if (reason) {
      invalidCheckedRows.push({
        rowNumber: rowNumber,
        invoiceNo: invoiceNo,
        closingNo: closingNo,
        reason: reason
      });
      continue;
    }
    records.push({
      rowNumber: rowNumber,
      invoiceNo: invoiceNo,
      closingNo: closingNo,
      prefix: prefix,
      stepType: prefix === '6101' ? 'cash' : 'cod',
      unpaidAmount: unpaidAmount,
      unpaidAmountText: String(unpaidAmount),
      customerId: toCollectionAiRemmiterText_(customerIdValues[index][0]),
      customerName: toCollectionAiRemmiterText_(customerNameValues[index][0]),
      currentComment: toCollectionAiRemmiterText_(commentValues[index][0]),
      iMatches: statusIndex[closingNo] || [],
      ledgerEntry: ledgerIndex[closingNo] || null
    });
  }

  const items = buildCollectionAiRemmiterGroupedItems_(records, invalidCheckedRows);
  let executableStepCount = 0;
  let skippedStepCount = 0;
  items.forEach(function(item) {
    [item.cashStep, item.codStep].forEach(function(step) {
      if (!step) return;
      if (step.decision === 'execute') executableStepCount++;
      else skippedStepCount++;
    });
  });
  return {
    items: items,
    invalidCheckedRows: invalidCheckedRows,
    scannedRows: numRows,
    checkedRows: records.length,
    executableStepCount: executableStepCount,
    skippedStepCount: skippedStepCount
  };
}

function emptyCollectionAiRemmiterQueue_() {
  return {
    items: [],
    invalidCheckedRows: [],
    scannedRows: 0,
    checkedRows: 0,
    executableStepCount: 0,
    skippedStepCount: 0
  };
}

function buildCollectionAiRemmiterGroupedItems_(records, invalidCheckedRows) {
  const grouped = {};
  const order = [];
  records.forEach(function(record) {
    if (!grouped[record.invoiceNo]) {
      grouped[record.invoiceNo] = [];
      order.push(record.invoiceNo);
    }
    grouped[record.invoiceNo].push(record);
  });
  const items = [];
  order.forEach(function(invoiceNo) {
    const rows = grouped[invoiceNo];
    const cashRows = rows.filter(function(row) { return row.prefix === '6101'; });
    const codRows = rows.filter(function(row) { return row.prefix === '6105'; });
    if (cashRows.length > 1 || codRows.length > 1) {
      rows.forEach(function(row) {
        invalidCheckedRows.push({
          rowNumber: row.rowNumber,
          invoiceNo: row.invoiceNo,
          closingNo: row.closingNo,
          reason: 'Ambiguous same-invoice duplicate closing nature.'
        });
      });
      return;
    }
    if (cashRows.length && codRows.length) {
      const payment = cashRows[0].unpaidAmount + codRows[0].unpaidAmount;
      if (!(payment > 0)) {
        rows.forEach(function(row) {
          invalidCheckedRows.push({
            rowNumber: row.rowNumber,
            invoiceNo: row.invoiceNo,
            closingNo: row.closingNo,
            reason: 'Paired payment must be positive.'
          });
        });
        return;
      }
      const item = buildCollectionAiRemmiterItem_('paired', invoiceNo, cashRows[0], codRows[0], payment);
      if (
        item.cashStep.decision === 'execute' &&
        item.codStep.decision === 'conflict'
      ) {
        item.cashStep.decision = 'conflict';
        item.cashStep.reason = 'Paired COD status conflict must be resolved before net cash receipt.';
      }
      items.push(item);
      return;
    }
    if (cashRows.length) {
      items.push(buildCollectionAiRemmiterItem_(
        'cashSolo', invoiceNo, cashRows[0], null, cashRows[0].unpaidAmount
      ));
      return;
    }
    if (codRows.length) {
      items.push(buildCollectionAiRemmiterItem_('codSolo', invoiceNo, null, codRows[0], null));
    }
  });
  return items;
}

function buildCollectionAiRemmiterItem_(groupType, invoiceNo, cashRow, codRow, cashAmount) {
  const cashStep = cashRow ? evaluateCollectionAiRemmiterStep_(cashRow) : null;
  const codStep = codRow ? evaluateCollectionAiRemmiterStep_(codRow) : null;
  return {
    groupType: groupType,
    invoiceNo: invoiceNo,
    rowNumbers: [cashRow, codRow].filter(Boolean).map(function(row) { return row.rowNumber; }),
    closingNumbers: [cashRow, codRow].filter(Boolean).map(function(row) { return row.closingNo; }),
    cashAmount: cashAmount == null ? null : cashAmount,
    cashAmountText: cashAmount == null ? '' : String(cashAmount),
    cashStep: cashStep,
    codStep: codStep
  };
}

function evaluateCollectionAiRemmiterStep_(row) {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const targetStatus = row.stepType === 'cash' ? cfg.cashStatus : cfg.codStatus;
  const matches = row.iMatches || [];
  const statusDecision = classifyCollectionAiRemmiterIStatuses_(
    matches.map(function(match) { return match.status; }),
    targetStatus
  );
  let decision = statusDecision.decision;
  let reason = statusDecision.reason;

  if (row.ledgerEntry) {
    decision = 'duplicate';
    reason = 'Closing number already exists in ARM_Remitter_Ledger.';
  } else if (row.currentComment) {
    decision = 'conflict';
    reason = 'Collection!T already contains text.';
  }

  return {
    stepType: row.stepType,
    rowNumber: row.rowNumber,
    invoiceNo: row.invoiceNo,
    closingNo: row.closingNo,
    unpaidAmount: row.unpaidAmount,
    unpaidAmountText: row.unpaidAmountText,
    customerId: row.customerId,
    customerName: row.customerName,
    targetIStatus: targetStatus,
    iMatchRows: matches.map(function(match) { return match.rowNumber; }),
    iWarning: matches.length ? '' : 'No Collection!E row matched ' + row.closingNo + '.',
    decision: decision,
    reason: reason
  };
}

function classifyCollectionAiRemmiterIStatuses_(statuses, targetStatus) {
  const nonBlank = (statuses || [])
    .map(toCollectionAiRemmiterText_)
    .filter(String);
  const conflicts = nonBlank.filter(function(status) { return status !== targetStatus; });
  if (conflicts.length) {
    return {
      decision: 'conflict',
      reason: 'Collection!I contains another status: ' + conflicts.join(', ')
    };
  }
  if (nonBlank.some(function(status) { return status === targetStatus; })) {
    return {
      decision: 'already_complete',
      reason: 'Collection!I already has the target status; review ledger and receipt.'
    };
  }
  return { decision: 'execute', reason: '' };
}

function beginCollectionAiRemmiterDirectRun_(workerId) {
  const worker = toCollectionAiRemmiterText_(workerId);
  if (!worker) throw new Error('workerId is required.');
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const existing = getCollectionAiRemmiterDirectRunLock_();
    if (existing.runId) {
      throw new Error(
        'A direct run is already locked by ' + existing.workerId + ': ' + existing.runId
      );
    }
    const queue = previewAiRemmiterQueueForWebApp_();
    if (!queue.executableStepCount) throw new Error('No executable checked steps were found.');
    const now = new Date();
    const run = {
      runId: 'ARM-DIRECT-' + Utilities.formatDate(now, 'Asia/Taipei', 'yyyyMMdd-HHmmss') +
        '-' + Utilities.getUuid().slice(0, 8),
      workerId: worker,
      startedAt: now.toISOString()
    };
    PropertiesService.getScriptProperties().setProperty(
      COLLECTION_AI_REMMITER_CFG.directRunProperty,
      JSON.stringify(run)
    );
    return Object.assign({}, queue, run);
  } finally {
    lock.releaseLock();
  }
}

function recordCollectionAiRemmiterDirectStep_(runId, workerId, step) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    return applyCollectionAiRemmiterDirectStep_(runId, workerId, step);
  } finally {
    lock.releaseLock();
  }
}

function applyCollectionAiRemmiterDirectStep_(runId, workerId, step) {
  const run = assertCollectionAiRemmiterDirectRun_(runId, workerId);
  if (!step || step.ok !== true) throw new Error('Only successful ARM steps may be recorded.');
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const closingNo = toCollectionAiRemmiterText_(step.closingNo);
  const receiptNo = toCollectionAiRemmiterText_(step.receiptNo);
  const stepType = toCollectionAiRemmiterText_(step.stepType);
  if (!cfg.closingNoPattern.test(closingNo)) throw new Error('Invalid closing number.');
  if (!cfg.receiptNoPattern.test(receiptNo)) throw new Error('Invalid ARM receipt number.');
  if (
    (stepType === 'cash' && closingNo.slice(0, 4) !== '6101') ||
    (stepType === 'cod' && closingNo.slice(0, 4) !== '6105') ||
    (stepType !== 'cash' && stepType !== 'cod')
  ) {
    throw new Error('Step type does not match the closing number.');
  }
  const paymentAmount = stepType === 'cash'
    ? toCollectionAiRemmiterNumber_(step.paymentAmount)
    : '';
  if (stepType === 'cash' && (!(paymentAmount > 0) || paymentAmount % 1 !== 0)) {
    throw new Error('Cash payment must be a positive whole number.');
  }
  const tComment = formatCollectionAiRemmiterTComment_(stepType, paymentAmount);
  const iStatus = stepType === 'cash' ? cfg.cashStatus : cfg.codStatus;

  const sheet = getCollectionAiRemmiterSheet_();
  const collectionRow = Number(step.rowNumber);
  const currentClosing = toCollectionAiRemmiterText_(
    sheet.getRange(collectionRow, cfg.closingNoCol).getDisplayValue()
  );
  if (currentClosing !== closingNo) {
    throw new Error('Collection!Q changed before result recording.');
  }
  const ledger = ensureCollectionAiRemmiterLedger_();
  if (readCollectionAiRemmiterLedgerIndex_(ledger)[closingNo]) {
    throw new Error('Closing number already exists in ARM_Remitter_Ledger.');
  }

  const iMatches = findCollectionAiRemmiterIMatches_(sheet, closingNo);
  const conflicts = iMatches.filter(function(match) {
    const status = toCollectionAiRemmiterText_(match.status);
    return status && status !== iStatus;
  });
  let iWarning = '';
  if (!iMatches.length) {
    iWarning = 'No Collection!E row matched ' + closingNo + '; I was not updated.';
  } else if (conflicts.length) {
    iWarning = 'Collection!I changed after preview; conflicting rows were not overwritten: ' +
      conflicts.map(function(match) { return match.rowNumber; }).join(', ');
  } else {
    iMatches.forEach(function(match) {
      sheet.getRange(match.rowNumber, cfg.leftStatusCol).setValue(iStatus);
    });
  }

  sheet.getRange(collectionRow, cfg.commentCol).setValue(tComment);
  const checkbox = sheet.getRange(collectionRow, cfg.checkboxCol);
  applyCollectionAiRemmiterCheckboxValidation_(checkbox);
  checkbox.setValue(false);
  appendCollectionAiRemmiterLedger_(ledger, {
    closingNo: closingNo,
    invoiceNo: toCollectionAiRemmiterText_(step.invoiceNo),
    tComment: tComment,
    completedAt: new Date(),
    receiptNo: receiptNo,
    runId: run.runId,
    stepType: stepType,
    paymentAmount: paymentAmount,
    iStatus: iStatus,
    iMatchRows: iMatches.map(function(match) { return match.rowNumber; }),
    iWarning: iWarning,
    evidenceDir: toCollectionAiRemmiterText_(step.evidenceDir),
    resultJson: JSON.stringify(step)
  });
  ensureCollectionAiRemmiterStatusOptions_(sheet);
  return {
    runId: run.runId,
    closingNo: closingNo,
    tComment: tComment,
    iStatus: iStatus,
    iMatchRows: iMatches.map(function(match) { return match.rowNumber; }),
    iWarning: iWarning
  };
}

function formatCollectionAiRemmiterTComment_(stepType, paymentAmount) {
  const stamp = Utilities.formatDate(new Date(), 'Asia/Taipei', 'M/d');
  if (stepType === 'cod') return stamp + ' 已折讓';
  const formatted = Math.round(paymentAmount)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return stamp + ' 已收 ' + formatted;
}

function releaseCollectionAiRemmiterDirectRun_(runId, workerId, summary) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const run = assertCollectionAiRemmiterDirectRun_(runId, workerId);
    appendCollectionAiRemmiterLog_({
      purpose: 'Release direct ARM remitter run',
      affectedColumns: 'Collection!I:I, Collection!T:U, ARM_Remitter_Ledger',
      keyVariables: 'runId=' + run.runId + ', summary=' + JSON.stringify(summary || {}),
      maintenanceNotes: 'Desktop direct run completed and released its remote lease.'
    });
    PropertiesService.getScriptProperties().deleteProperty(
      COLLECTION_AI_REMMITER_CFG.directRunProperty
    );
    return { released: true, runId: run.runId };
  } finally {
    lock.releaseLock();
  }
}

function getCollectionAiRemmiterDirectRunLock_() {
  const value = PropertiesService.getScriptProperties().getProperty(
    COLLECTION_AI_REMMITER_CFG.directRunProperty
  );
  if (!value) return {};
  try {
    return JSON.parse(value);
  } catch (err) {
    return { runId: 'INVALID-LOCK', workerId: '', startedAt: '', parseError: String(err) };
  }
}

function clearCollectionAiRemmiterDirectRunLock_(confirmation) {
  if (toCollectionAiRemmiterText_(confirmation) !== 'CLEAR DIRECT RUN') {
    throw new Error('Exact confirmation text is required: CLEAR DIRECT RUN');
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const previous = getCollectionAiRemmiterDirectRunLock_();
    PropertiesService.getScriptProperties().deleteProperty(
      COLLECTION_AI_REMMITER_CFG.directRunProperty
    );
    return { cleared: true, previous: previous };
  } finally {
    lock.releaseLock();
  }
}

function showCollectionAiRemmiterDirectRunLock() {
  const value = getCollectionAiRemmiterDirectRunLock_();
  showCollectionAiRemmiterAlert_(value.runId ? JSON.stringify(value, null, 2) : 'No direct-run lock.');
  return value;
}

function clearCollectionAiRemmiterDirectRunLockFromMenu() {
  const ui = SpreadsheetApp.getUi();
  const response = ui.prompt(
    'Clear reviewed direct-run lock',
    'First verify ARM, receipts, Collection!T/I/U, ledger, and evidence.\n' +
      'Type CLEAR DIRECT RUN to clear the lock.',
    ui.ButtonSet.OK_CANCEL
  );
  if (response.getSelectedButton() !== ui.Button.OK) return { cleared: false };
  return clearCollectionAiRemmiterDirectRunLock_(response.getResponseText());
}

function assertCollectionAiRemmiterDirectRun_(runId, workerId) {
  const run = getCollectionAiRemmiterDirectRunLock_();
  if (!run.runId) throw new Error('No direct-run lock exists.');
  if (run.runId !== toCollectionAiRemmiterText_(runId)) throw new Error('Direct-run ID mismatch.');
  if (run.workerId !== toCollectionAiRemmiterText_(workerId)) throw new Error('Direct-run worker mismatch.');
  return run;
}

function buildCollectionAiRemmiterIStatusIndex_(sheet) {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const lastRow = Math.max(sheet.getLastRow(), cfg.startRow);
  const numRows = lastRow - cfg.startRow + 1;
  const closings = sheet.getRange(cfg.startRow, cfg.leftClosingNoCol, numRows, 1).getDisplayValues();
  const statuses = sheet.getRange(cfg.startRow, cfg.leftStatusCol, numRows, 1).getDisplayValues();
  const index = {};
  for (let i = 0; i < numRows; i++) {
    const closingNo = toCollectionAiRemmiterText_(closings[i][0]);
    if (!closingNo) continue;
    if (!index[closingNo]) index[closingNo] = [];
    index[closingNo].push({
      rowNumber: cfg.startRow + i,
      status: toCollectionAiRemmiterText_(statuses[i][0])
    });
  }
  return index;
}

function findCollectionAiRemmiterIMatches_(sheet, closingNo) {
  return buildCollectionAiRemmiterIStatusIndex_(sheet)[closingNo] || [];
}

function ensureCollectionAiRemmiterLedger_() {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
  let sheet = ss.getSheetByName(cfg.ledgerSheetName);
  if (!sheet) sheet = ss.insertSheet(cfg.ledgerSheetName);
  const headers = [
    'closing_no', 'invoice_no', 'status_text', 'completed_at', 'receipt_no',
    'request_id', 'result_json', 'step_type', 'payment_amount', 'i_status',
    'i_match_rows_json', 'i_warning', 'evidence_dir'
  ];
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
  } else if (sheet.getLastColumn() < headers.length) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
  if (!sheet.isSheetHidden()) sheet.hideSheet();
  return sheet;
}

function readCollectionAiRemmiterLedgerIndex_(ledgerSheet) {
  const values = ledgerSheet.getDataRange().getValues();
  const index = {};
  for (let row = 1; row < values.length; row++) {
    const closingNo = toCollectionAiRemmiterText_(values[row][0]);
    if (closingNo && !index[closingNo]) {
      index[closingNo] = { rowNumber: row + 1, receiptNo: values[row][4] };
    }
  }
  return index;
}

function appendCollectionAiRemmiterLedger_(ledgerSheet, entry) {
  if (readCollectionAiRemmiterLedgerIndex_(ledgerSheet)[entry.closingNo]) {
    throw new Error('Duplicate ledger closing number: ' + entry.closingNo);
  }
  ledgerSheet.appendRow([
    entry.closingNo,
    entry.invoiceNo,
    entry.tComment,
    entry.completedAt,
    entry.receiptNo,
    entry.runId,
    entry.resultJson,
    entry.stepType,
    entry.paymentAmount,
    entry.iStatus,
    JSON.stringify(entry.iMatchRows || []),
    entry.iWarning,
    entry.evidenceDir
  ]);
}

function ensureCollectionAiRemmiterStatusOptions_(sheet) {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const lastRow = Math.max(sheet.getLastRow(), cfg.startRow);
  const numRows = lastRow - cfg.startRow + 1;
  [cfg.leftStatusCol, cfg.archiveStatusCol].forEach(function(column) {
    const range = sheet.getRange(cfg.startRow, column, numRows, 1);
    const currentRule = range.getCell(1, 1).getDataValidation();
    let options = [];
    if (currentRule) {
      const criteria = currentRule.getCriteriaValues();
      if (criteria && Array.isArray(criteria[0])) options = criteria[0].slice();
    }
    [cfg.cashStatus, cfg.codStatus].forEach(function(status) {
      if (options.indexOf(status) < 0) options.push(status);
    });
    if (!options.length) options = [cfg.cashStatus, cfg.codStatus];
    const rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(options, true)
      .setAllowInvalid(true)
      .build();
    range.setDataValidation(rule);
  });
}

function handleCollectionAiRemmiterEdit_(e) {
  if (!e || !e.range) return;
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const sheet = e.range.getSheet();
  if (sheet.getName() !== cfg.sheetName) return;
  if (e.range.getColumn() !== cfg.checkboxCol || e.range.getRow() < cfg.startRow) return;
  const closingNo = toCollectionAiRemmiterText_(
    sheet.getRange(e.range.getRow(), cfg.closingNoCol).getDisplayValue()
  );
  if (!closingNo && isCollectionAiRemmiterChecked_(e.value)) {
    e.range.setValue(false);
  }
  applyCollectionAiRemmiterCheckboxValidation_(e.range);
}

function applyCollectionAiRemmiterCheckboxValidation_(range) {
  const rule = SpreadsheetApp.newDataValidation()
    .requireCheckbox()
    .setAllowInvalid(false)
    .build();
  range.setDataValidation(rule);
}

function getCollectionAiRemmiterSheet_() {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const sheet = SpreadsheetApp.openById(cfg.spreadsheetId).getSheetByName(cfg.sheetName);
  if (!sheet) throw new Error('Missing sheet: ' + cfg.sheetName);
  return sheet;
}

function isCollectionAiRemmiterChecked_(value) {
  if (value === true) return true;
  const text = toCollectionAiRemmiterText_(value).toUpperCase();
  return text === 'TRUE' || text === 'YES' || text === 'Y' || text === '1';
}

function toCollectionAiRemmiterNumber_(value) {
  if (value === '' || value == null) return 0;
  if (typeof value === 'number') return value;
  const parsed = Number(String(value).replace(/,/g, '').trim());
  return isNaN(parsed) ? 0 : parsed;
}

function toCollectionAiRemmiterText_(value) {
  return value == null ? '' : String(value).trim();
}

function appendCollectionAiRemmiterLog_(info) {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
  let sheet = ss.getSheetByName(cfg.logSheetName);
  if (!sheet) sheet = ss.insertSheet(cfg.logSheetName);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow([
      'DateTime', 'Process Name', 'Purpose', 'Affected Sheets',
      'Affected Columns', 'Key Variables', 'Maintenance Notes'
    ]);
  }
  sheet.appendRow([
    new Date(),
    cfg.processName,
    info.purpose || '',
    cfg.sheetName + ', ' + cfg.ledgerSheetName + ', ' + cfg.logSheetName,
    info.affectedColumns || '',
    info.keyVariables || '',
    info.maintenanceNotes || ''
  ]);
}

function showCollectionAiRemmiterAlert_(message) {
  try {
    SpreadsheetApp.getUi().alert(message);
  } catch (err) {
    Logger.log('[INFO] AI Remitter alert skipped: ' + err);
  }
}
