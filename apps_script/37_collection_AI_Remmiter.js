const COLLECTION_AI_REMMITER_CFG = {
  spreadsheetId: '1eTnZppbhu7fpwdFTrnFoQmxchylsZus0Sw4j1t61Zzo',
  sheetName: 'Collection',
  headerRow: 2,
  startRow: 3,
  invoiceNoCol: 16, // P
  closingNoCol: 17, // Q
  unpaidCol: 19, // S
  checkboxCol: 21, // U, also final AI Remmiter status
  completedValue: '\u5df2\u532f\u6b3e',
  maxRows: 5000,
  closingNoPattern: /^61\d{2}-\d{10}$/,
  logSheetName: 'LOG',
  processName: 'Collection AI Remmiter'
};

function buildCollectionAiRemmiterMenu_(ui) {
  ui.createMenu('AI Remmiter')
    .addItem('Setup checkboxes', 'setupCollectionAiRemmiterCheckboxes')
    .addItem('Preview queue only', 'previewCollectionAiRemmiterQueue')
    .addItem('Show local run command', 'showCollectionAiRemmiterRunCommand')
    .addToUi();
}

function setupCollectionAiRemmiterCheckboxes() {
  const sheet = getCollectionAiRemmiterSheet_();
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const lastRow = Math.max(sheet.getLastRow(), cfg.startRow);
  const endRow = Math.min(Math.max(sheet.getMaxRows(), lastRow), cfg.maxRows);
  const numRows = Math.max(endRow - cfg.startRow + 1, 1);
  const range = sheet.getRange(cfg.startRow, cfg.checkboxCol, numRows, 1);
  const values = range.getValues();
  const normalized = values.map(function(row) {
    const value = row[0];
    if (value === true || value === false) return [value];
    if (toCollectionAiRemmiterText_(value) === cfg.completedValue) return [cfg.completedValue];
    const text = toCollectionAiRemmiterText_(value).toUpperCase();
    if (text === 'TRUE' || text === 'YES' || text === 'Y' || text === '1') return [true];
    return [false];
  });

  const rule = SpreadsheetApp.newDataValidation()
    .requireCheckbox()
    .setAllowInvalid(false)
    .build();

  range.setDataValidation(rule);
  range.setValues(normalized);
  normalized.forEach(function(row, index) {
    if (row[0] === cfg.completedValue) {
      sheet.getRange(cfg.startRow + index, cfg.checkboxCol).clearDataValidations();
    }
  });

  const queue = buildCollectionAiRemmiterQueue_(sheet);
  appendCollectionAiRemmiterLog_({
    purpose: 'Setup AI Remmiter checkboxes',
    affectedColumns: cfg.sheetName + '!U:U',
    keyVariables:
      'checkboxRows=' +
      numRows +
      ', checkedValidRows=' +
      queue.items.length +
      ', checkedInvalidRows=' +
      queue.invalidCheckedRows.length,
    maintenanceNotes: 'Prepared Collection!U checkboxes for local ARM AI Remmiter batch processing.'
  });

  return {
    checkboxRows: numRows,
    checkedValidRows: queue.items.length,
    checkedInvalidRows: queue.invalidCheckedRows.length,
    range: cfg.sheetName + '!U' + cfg.startRow + ':U' + endRow
  };
}

function previewCollectionAiRemmiterQueue() {
  setupCollectionAiRemmiterCheckboxes();
  const result = getCollectionAiRemmiterQueue();
  const message =
    'AI Remmiter queue: ' +
    result.items.length +
    ' valid checked row(s), ' +
    result.invalidCheckedRows.length +
    ' invalid checked row(s). Browser automation is local; run python collection_ai_remmiter.py --limit 1.';
  showCollectionAiRemmiterAlert_(message);
  return result;
}

function showCollectionAiRemmiterRunCommand() {
  const message =
    'Apps Script prepares the queue only. To launch ARM browser automation, run locally:\n\n' +
    'python collection_ai_remmiter.py --dry-run\n' +
    'python collection_ai_remmiter.py --limit 1';
  showCollectionAiRemmiterAlert_(message);
  return message;
}

function getCollectionAiRemmiterQueue() {
  const sheet = getCollectionAiRemmiterSheet_();
  const queue = buildCollectionAiRemmiterQueue_(sheet);

  appendCollectionAiRemmiterLog_({
    purpose: 'Get AI Remmiter checked queue',
    affectedColumns:
      COLLECTION_AI_REMMITER_CFG.sheetName +
      '!P:P, ' +
      COLLECTION_AI_REMMITER_CFG.sheetName +
      '!Q:Q, ' +
      COLLECTION_AI_REMMITER_CFG.sheetName +
      '!S:S, ' +
      COLLECTION_AI_REMMITER_CFG.sheetName +
      '!U:U',
    keyVariables:
      'checkedValidRows=' +
      queue.items.length +
      ', checkedInvalidRows=' +
      queue.invalidCheckedRows.length,
    maintenanceNotes: 'Returned checked Collection!U rows grouped by invoice number to local Python.'
  });

  return queue;
}

function recordCollectionAiRemmiterResults(results) {
  if (results === undefined) {
    const message =
      'recordCollectionAiRemmiterResults is called by local Python after browser automation. ' +
      'Run python collection_ai_remmiter.py --limit 1 instead.';
    showCollectionAiRemmiterAlert_(message);
    return {
      receivedResults: 0,
      successCount: 0,
      failureCount: 0,
      skippedCount: 0,
      message: message
    };
  }

  if (!Array.isArray(results)) {
    throw new Error('results must be an array.');
  }

  const sheet = getCollectionAiRemmiterSheet_();
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const resultsByGroup = [];
  let successCount = 0;
  let failureCount = 0;
  let skippedCount = 0;

  results.forEach(function(result) {
    const rowNumbers = getCollectionAiRemmiterResultRowNumbers_(result);
    if (!rowNumbers.length) {
      skippedCount++;
      return;
    }
    resultsByGroup.push({
      result: result,
      rowNumbers: rowNumbers
    });
  });

  resultsByGroup.forEach(function(groupResult) {
    const result = groupResult.result || {};
    const ok = result.ok === true;
    const rowNumbers = groupResult.rowNumbers;
    const closingNos = getCollectionAiRemmiterResultClosingNos_(result);
    const rowCheck = validateCollectionAiRemmiterResultRows_(sheet, rowNumbers, closingNos);
    const groupOk = ok && rowCheck.ok;

    rowNumbers.forEach(function(rowNumber) {
      if (groupOk) {
      sheet.getRange(rowNumber, cfg.checkboxCol).clearDataValidations().setValue(cfg.completedValue);
      } else {
      applyCollectionAiRemmiterCheckboxValidation_(sheet.getRange(rowNumber, cfg.checkboxCol));
      sheet.getRange(rowNumber, cfg.checkboxCol).setValue(false);
      }
    });

    if (groupOk) successCount += rowNumbers.length;
    else failureCount += rowNumbers.length;
  });

  appendCollectionAiRemmiterLog_({
    purpose: 'Record AI Remmiter results',
    affectedColumns: cfg.sheetName + '!U:U',
    keyVariables:
      'receivedResults=' +
      results.length +
      ', successCount=' +
      successCount +
      ', failureCount=' +
      failureCount +
      ', skippedCount=' +
      skippedCount,
    maintenanceNotes:
      'Local Python finished grouped ARM remitter actions. Collection!U is ' +
      cfg.completedValue +
      ' for successful group rows and FALSE for failed group rows.'
  });

  return {
    receivedResults: results.length,
    successCount: successCount,
    failureCount: failureCount,
    skippedCount: skippedCount
  };
}

function buildCollectionAiRemmiterQueue_(sheet) {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const lastRow = Math.min(Math.max(sheet.getLastRow(), cfg.startRow), cfg.maxRows);
  const numRows = Math.max(lastRow - cfg.startRow + 1, 0);
  if (!numRows) {
    return {
      items: [],
      invalidCheckedRows: [],
      scannedRows: 0
    };
  }

  const invoiceValues = sheet.getRange(cfg.startRow, cfg.invoiceNoCol, numRows, 1).getDisplayValues();
  const closingValues = sheet.getRange(cfg.startRow, cfg.closingNoCol, numRows, 1).getDisplayValues();
  const unpaidValues = sheet.getRange(cfg.startRow, cfg.unpaidCol, numRows, 1).getDisplayValues();
  const checkboxValues = sheet.getRange(cfg.startRow, cfg.checkboxCol, numRows, 1).getValues();
  const invalidCheckedRows = [];
  const records = [];

  for (let i = 0; i < numRows; i++) {
    if (!isCollectionAiRemmiterChecked_(checkboxValues[i][0])) continue;

    const rowNumber = cfg.startRow + i;
    const invoiceNo = toCollectionAiRemmiterText_(invoiceValues[i][0]);
    const closingNo = toCollectionAiRemmiterText_(closingValues[i][0]);
    const unpaidText = toCollectionAiRemmiterText_(unpaidValues[i][0]);
    const unpaidAmount = toCollectionAiRemmiterNumber_(unpaidText);
    const prefix = closingNo.slice(0, 4);

    if (!invoiceNo) {
      invalidCheckedRows.push({
        rowNumber: rowNumber,
        invoiceNo: invoiceNo,
        closingNo: closingNo,
        reason: 'Blank Collection!P invoice number.'
      });
      continue;
    }

    if (!cfg.closingNoPattern.test(closingNo)) {
      invalidCheckedRows.push({
        rowNumber: rowNumber,
        invoiceNo: invoiceNo,
        closingNo: closingNo,
        reason: 'Invalid or blank Collection!Q closing number.'
      });
      continue;
    }

    if (unpaidAmount === 0) {
      invalidCheckedRows.push({
        rowNumber: rowNumber,
        invoiceNo: invoiceNo,
        closingNo: closingNo,
        unpaidAmount: unpaidText,
        reason: 'Invalid or zero Collection!S unpaid amount.'
      });
      continue;
    }

    if (prefix === '6101' && !(unpaidAmount > 0)) {
      invalidCheckedRows.push({
        rowNumber: rowNumber,
        invoiceNo: invoiceNo,
        closingNo: closingNo,
        unpaidAmount: unpaidText,
        reason: '6101 cash row must have a positive unpaid amount.'
      });
      continue;
    }

    if (prefix === '6105' && !(unpaidAmount < 0)) {
      invalidCheckedRows.push({
        rowNumber: rowNumber,
        invoiceNo: invoiceNo,
        closingNo: closingNo,
        unpaidAmount: unpaidText,
        reason: '6105 COD row must have a negative unpaid amount.'
      });
      continue;
    }

    if (prefix !== '6101' && prefix !== '6105') {
      invalidCheckedRows.push({
        rowNumber: rowNumber,
        invoiceNo: invoiceNo,
        closingNo: closingNo,
        unpaidAmount: unpaidText,
        reason: 'Unsupported closing number prefix. Expected 6101 or 6105.'
      });
      continue;
    }

    records.push({
      rowNumber: rowNumber,
      invoiceNo: invoiceNo,
      closingNo: closingNo,
      prefix: prefix,
      unpaidAmount: unpaidAmount,
      unpaidAmountText: String(unpaidAmount)
    });
  }

  const grouped = buildCollectionAiRemmiterGroupedItems_(records, invalidCheckedRows);

  return {
    items: grouped.items,
    invalidCheckedRows: invalidCheckedRows,
    scannedRows: numRows,
    checkedRows: records.length
  };
}

function buildCollectionAiRemmiterGroupedItems_(records, invalidCheckedRows) {
  const byInvoice = {};
  const invoiceOrder = [];
  records.forEach(function(record) {
    if (!byInvoice[record.invoiceNo]) {
      byInvoice[record.invoiceNo] = [];
      invoiceOrder.push(record.invoiceNo);
    }
    byInvoice[record.invoiceNo].push(record);
  });

  const items = [];
  invoiceOrder.forEach(function(invoiceNo) {
    const rows = byInvoice[invoiceNo];
    const cashRows = rows.filter(function(row) { return row.prefix === '6101'; });
    const codRows = rows.filter(function(row) { return row.prefix === '6105'; });

    if (cashRows.length > 1 || codRows.length > 1) {
      rows.forEach(function(row) {
        invalidCheckedRows.push({
          rowNumber: row.rowNumber,
          invoiceNo: row.invoiceNo,
          closingNo: row.closingNo,
          unpaidAmount: row.unpaidAmountText,
          reason: 'Ambiguous same-invoice duplicates. Expected at most one 6101 and one 6105 row.'
        });
      });
      return;
    }

    if (cashRows.length === 1 && codRows.length === 1) {
      const cash = cashRows[0];
      const cod = codRows[0];
      const cashAmount = cash.unpaidAmount + cod.unpaidAmount;
      if (!(cashAmount > 0)) {
        [cash, cod].forEach(function(row) {
          invalidCheckedRows.push({
            rowNumber: row.rowNumber,
            invoiceNo: row.invoiceNo,
            closingNo: row.closingNo,
            unpaidAmount: row.unpaidAmountText,
            reason: 'Paired net cash amount must be positive.'
          });
        });
        return;
      }
      items.push(buildCollectionAiRemmiterItem_('paired', invoiceNo, cash, cod, cashAmount));
      return;
    }

    if (cashRows.length === 1) {
      const cashSolo = cashRows[0];
      items.push(buildCollectionAiRemmiterItem_('cashSolo', invoiceNo, cashSolo, null, cashSolo.unpaidAmount));
      return;
    }

    if (codRows.length === 1) {
      items.push(buildCollectionAiRemmiterItem_('codSolo', invoiceNo, null, codRows[0], null));
    }
  });

  return {
    items: items
  };
}

function buildCollectionAiRemmiterItem_(groupType, invoiceNo, cashRow, codRow, cashAmount) {
  const rowNumbers = [];
  if (cashRow) rowNumbers.push(cashRow.rowNumber);
  if (codRow) rowNumbers.push(codRow.rowNumber);

  return {
    groupType: groupType,
    invoiceNo: invoiceNo,
    rowNumbers: rowNumbers,
    closingNumbers: rowNumbers.map(function(rowNumber) {
      if (cashRow && cashRow.rowNumber === rowNumber) return cashRow.closingNo;
      if (codRow && codRow.rowNumber === rowNumber) return codRow.closingNo;
      return '';
    }),
    cashAmount: cashAmount == null ? null : cashAmount,
    cashAmountText: cashAmount == null ? '' : String(cashAmount),
    cashStep: cashRow ? cloneCollectionAiRemmiterStep_(cashRow) : null,
    codStep: codRow ? cloneCollectionAiRemmiterStep_(codRow) : null
  };
}

function cloneCollectionAiRemmiterStep_(row) {
  return {
    rowNumber: row.rowNumber,
    invoiceNo: row.invoiceNo,
    closingNo: row.closingNo,
    unpaidAmount: row.unpaidAmount,
    unpaidAmountText: row.unpaidAmountText
  };
}

function getCollectionAiRemmiterResultRowNumbers_(result) {
  if (!result) return [];
  const source = Array.isArray(result.rowNumbers) ? result.rowNumbers : [result.rowNumber];
  const seen = {};
  const rowNumbers = [];
  source.forEach(function(value) {
    const rowNumber = Number(value);
    if (!rowNumber || rowNumber < COLLECTION_AI_REMMITER_CFG.startRow || seen[rowNumber]) return;
    seen[rowNumber] = true;
    rowNumbers.push(rowNumber);
  });
  return rowNumbers;
}

function getCollectionAiRemmiterResultClosingNos_(result) {
  const closingNos = {};
  if (!result) return closingNos;
  if (Array.isArray(result.steps)) {
    result.steps.forEach(function(step) {
      if (!step || !step.rowNumber) return;
      closingNos[Number(step.rowNumber)] = toCollectionAiRemmiterText_(step.closingNo);
    });
  }
  if (result.rowNumber && result.closingNo) {
    closingNos[Number(result.rowNumber)] = toCollectionAiRemmiterText_(result.closingNo);
  }
  if (Array.isArray(result.rowNumbers) && Array.isArray(result.closingNumbers)) {
    result.rowNumbers.forEach(function(rowNumber, index) {
      closingNos[Number(rowNumber)] = toCollectionAiRemmiterText_(result.closingNumbers[index]);
    });
  }
  return closingNos;
}

function validateCollectionAiRemmiterResultRows_(sheet, rowNumbers, closingNos) {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  for (let i = 0; i < rowNumbers.length; i++) {
    const rowNumber = rowNumbers[i];
    const expectedClosingNo = toCollectionAiRemmiterText_(closingNos[rowNumber]);
    if (!expectedClosingNo) continue;
    const currentClosingNo = toCollectionAiRemmiterText_(sheet.getRange(rowNumber, cfg.closingNoCol).getValue());
    if (expectedClosingNo !== currentClosingNo) {
      return {
        ok: false,
        message: 'Row ' + rowNumber + ' closing number changed from ' + expectedClosingNo + ' to ' + currentClosingNo + '.'
      };
    }
  }
  return { ok: true, message: '' };
}

function getCollectionAiRemmiterSheet_() {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
  const sheet = ss.getSheetByName(cfg.sheetName);
  if (!sheet) throw new Error('Missing sheet: ' + cfg.sheetName);
  return sheet;
}

function isCollectionAiRemmiterChecked_(value) {
  if (value === true) return true;
  const text = toCollectionAiRemmiterText_(value).toUpperCase();
  return text === 'TRUE' || text === 'YES' || text === 'Y' || text === '1';
}

function applyCollectionAiRemmiterCheckboxValidation_(range) {
  const rule = SpreadsheetApp.newDataValidation()
    .requireCheckbox()
    .setAllowInvalid(false)
    .build();
  range.setDataValidation(rule);
}

function toCollectionAiRemmiterNumber_(value) {
  if (value === '' || value == null) return 0;
  if (typeof value === 'number') return value;
  const parsed = Number(String(value).replace(/,/g, '').trim());
  return isNaN(parsed) ? 0 : parsed;
}

function appendCollectionAiRemmiterLog_(info) {
  const cfg = COLLECTION_AI_REMMITER_CFG;
  const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
  let logSheet = ss.getSheetByName(cfg.logSheetName);
  if (!logSheet) logSheet = ss.insertSheet(cfg.logSheetName);

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
    cfg.processName,
    info.purpose || '',
    cfg.sheetName + ', ' + cfg.logSheetName,
    info.affectedColumns || '',
    info.keyVariables || '',
    info.maintenanceNotes || ''
  ]);
}

function showCollectionAiRemmiterAlert_(message) {
  try {
    SpreadsheetApp.getUi().alert(message);
  } catch (err) {
    Logger.log('[INFO] AI Remmiter alert skipped: ' + err);
  }
}

function toCollectionAiRemmiterText_(value) {
  return value == null ? '' : String(value).trim();
}
