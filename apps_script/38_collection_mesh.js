const COLLECTION_MESH_CFG = {
  spreadsheetId: '1eTnZppbhu7fpwdFTrnFoQmxchylsZus0Sw4j1t61Zzo',
  destinationSheetName: 'V',
  ledgerSheetName: 'ARM_Mesh_Ledger',
  startRow: 3,
  destinationWidth: 20, // A:T
  customerIdCol: 1, // A
  reportDateCol: 8, // H
  customerNameCol: 15, // O
  journalCol: 20, // T
  closingNoPattern: /^61\d{2}-\d{10}$/
};

function appendCollectionMeshCustomerQueue_(steps, runId) {
  const cfg = COLLECTION_MESH_CFG;
  if (!Array.isArray(steps)) throw new Error('steps must be an array.');

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const ss = SpreadsheetApp.openById(cfg.spreadsheetId);
    const ledger = ensureCollectionMeshLedger_(ss);
    const ledgerIndex = readCollectionMeshLedgerIndex_(ledger);
    const now = new Date();
    const batchId = 'MESH-' +
      Utilities.formatDate(now, 'Asia/Taipei', 'yyyyMMdd-HHmmss') +
      '-' + Utilities.getUuid().slice(0, 8);
    const reportDate = Utilities.formatDate(now, 'Asia/Taipei', 'yyyy/MM/dd');
    const plan = buildCollectionMeshPlan_(
      steps,
      ledgerIndex,
      toCollectionMeshText_(runId),
      batchId,
      reportDate
    );
    const ledgerRows = plan.skipped.map(function(item) {
      return buildCollectionMeshLedgerRow_(item, 'skipped', '', item.reason);
    });

    if (plan.groups.length) {
      const destination = ss.getSheetByName(cfg.destinationSheetName);
      if (!destination) {
        plan.groups.forEach(function(group) {
          group.steps.forEach(function(step) {
            const skipped = Object.assign({}, step, {
              runId: plan.runId,
              batchId: plan.batchId,
              reportDate: plan.reportDate,
              journal: group.journal,
              reason: 'Missing destination sheet: ' + cfg.destinationSheetName
            });
            plan.skipped.push(skipped);
            ledgerRows.push(buildCollectionMeshLedgerRow_(
              skipped, 'skipped', '', skipped.reason
            ));
          });
        });
        plan.groups = [];
      } else {
        const startRow = findCollectionMeshDestinationRow_(destination);
        const values = plan.groups.map(function(group) {
          return buildCollectionMeshDestinationRow_(group, plan.reportDate);
        });
        try {
          destination
            .getRange(startRow, 1, values.length, cfg.destinationWidth)
            .setValues(values);
          plan.groups.forEach(function(group, index) {
            group.destinationRow = startRow + index;
            group.steps.forEach(function(step) {
              ledgerRows.push(buildCollectionMeshLedgerRow_(
                Object.assign({}, step, {
                  runId: plan.runId,
                  batchId: plan.batchId,
                  reportDate: plan.reportDate,
                  journal: group.journal
                }),
                'appended',
                group.destinationRow,
                ''
              ));
            });
          });
        } catch (err) {
          plan.groups.forEach(function(group) {
            group.steps.forEach(function(step) {
              const skipped = Object.assign({}, step, {
                runId: plan.runId,
                batchId: plan.batchId,
                reportDate: plan.reportDate,
                journal: group.journal,
                reason: 'Destination write failed: ' + err.message
              });
              plan.skipped.push(skipped);
              ledgerRows.push(buildCollectionMeshLedgerRow_(
                skipped, 'skipped', '', skipped.reason
              ));
            });
          });
          plan.groups = [];
        }
      }
    }

    if (ledgerRows.length) {
      ledger.getRange(
        ledger.getLastRow() + 1,
        1,
        ledgerRows.length,
        ledgerRows[0].length
      ).setValues(ledgerRows);
    }

    return summarizeCollectionMeshPlan_(plan);
  } finally {
    lock.releaseLock();
  }
}

function buildCollectionMeshPlan_(steps, ledgerIndex, runId, batchId, reportDate) {
  const cfg = COLLECTION_MESH_CFG;
  const grouped = {};
  const order = [];
  const skipped = [];
  const duplicates = [];
  const seen = {};

  (steps || []).forEach(function(raw) {
    const step = {
      runId: runId,
      batchId: batchId,
      reportDate: reportDate,
      closingNo: toCollectionMeshText_(raw && raw.closingNo),
      stepType: toCollectionMeshText_(raw && raw.stepType),
      customerId: toCollectionMeshText_(raw && raw.customerId),
      customerName: toCollectionMeshText_(raw && raw.customerName),
      invoiceNo: toCollectionMeshText_(raw && raw.invoiceNo),
      receiptNo: toCollectionMeshText_(raw && raw.receiptNo)
    };
    if (ledgerIndex[step.closingNo]) {
      duplicates.push(step.closingNo);
      return;
    }
    if (seen[step.closingNo]) {
      duplicates.push(step.closingNo);
      return;
    }
    if (step.closingNo) seen[step.closingNo] = true;
    let reason = '';
    if (!cfg.closingNoPattern.test(step.closingNo)) {
      reason = 'Invalid closing number.';
    } else if (
      (step.stepType === 'cash' && step.closingNo.slice(0, 4) !== '6101') ||
      (step.stepType === 'cod' && step.closingNo.slice(0, 4) !== '6105') ||
      (step.stepType !== 'cash' && step.stepType !== 'cod')
    ) {
      reason = 'Step type does not match closing number.';
    } else if (!step.customerId) {
      reason = 'Blank customer ID.';
    } else if (!step.customerName) {
      reason = 'Blank customer name.';
    }
    if (reason) {
      step.reason = reason;
      skipped.push(step);
      return;
    }
    if (!grouped[step.customerId]) {
      grouped[step.customerId] = [];
      order.push(step.customerId);
    }
    grouped[step.customerId].push(step);
  });

  const groups = [];
  order.forEach(function(customerId) {
    const customerSteps = grouped[customerId];
    const names = [];
    customerSteps.forEach(function(step) {
      if (names.indexOf(step.customerName) < 0) names.push(step.customerName);
    });
    if (names.length !== 1) {
      customerSteps.forEach(function(step) {
        step.reason = 'Conflicting customer names for customer ID ' + customerId + '.';
        skipped.push(step);
      });
      return;
    }
    groups.push({
      customerId: customerId,
      customerName: names[0],
      journal: getCollectionMeshJournal_(customerSteps),
      closingNumbers: customerSteps.map(function(step) { return step.closingNo; }),
      steps: customerSteps
    });
  });

  return {
    runId: runId,
    batchId: batchId,
    reportDate: reportDate,
    receivedStepCount: (steps || []).length,
    groups: groups,
    skipped: skipped,
    duplicateClosingNumbers: duplicates
  };
}

function getCollectionMeshJournal_(steps) {
  const hasCash = (steps || []).some(function(step) { return step.stepType === 'cash'; });
  const hasCod = (steps || []).some(function(step) { return step.stepType === 'cod'; });
  if (hasCash && hasCod) return '寄單、收款成功';
  if (hasCod) return '寄單';
  return '收款成功';
}

function buildCollectionMeshDestinationRow_(group, reportDate) {
  const cfg = COLLECTION_MESH_CFG;
  const row = new Array(cfg.destinationWidth).fill('');
  row[cfg.customerIdCol - 1] = group.customerId;
  row[cfg.reportDateCol - 1] = reportDate;
  row[cfg.customerNameCol - 1] = group.customerName;
  row[cfg.journalCol - 1] = group.journal;
  return row;
}

function summarizeCollectionMeshPlan_(plan) {
  const appendedGroups = plan.groups.map(function(group) {
    return {
      customerId: group.customerId,
      customerName: group.customerName,
      journal: group.journal,
      closingNumbers: group.closingNumbers,
      destinationRow: group.destinationRow
    };
  });
  return {
    batchId: plan.batchId,
    runId: plan.runId,
    reportDate: plan.reportDate,
    receivedStepCount: plan.receivedStepCount,
    appendedGroupCount: appendedGroups.length,
    appendedClosingCount: appendedGroups.reduce(function(total, group) {
      return total + group.closingNumbers.length;
    }, 0),
    duplicateClosingCount: plan.duplicateClosingNumbers.length,
    skippedClosingCount: plan.skipped.length,
    appendedGroups: appendedGroups,
    duplicateClosingNumbers: plan.duplicateClosingNumbers,
    skipped: plan.skipped.map(function(step) {
      return {
        closingNo: step.closingNo,
        customerId: step.customerId,
        customerName: step.customerName,
        reason: step.reason
      };
    })
  };
}

function ensureCollectionMeshLedger_(ss) {
  const cfg = COLLECTION_MESH_CFG;
  let sheet = ss.getSheetByName(cfg.ledgerSheetName);
  if (!sheet) sheet = ss.insertSheet(cfg.ledgerSheetName);
  const headers = [
    'closing_no', 'status', 'processed_at', 'run_id', 'batch_id',
    'customer_id', 'customer_name', 'step_type', 'invoice_no', 'receipt_no',
    'report_date', 'journal', 'destination_row', 'reason'
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

function readCollectionMeshLedgerIndex_(sheet) {
  const values = sheet.getDataRange().getValues();
  const index = {};
  for (let row = 1; row < values.length; row++) {
    const closingNo = toCollectionMeshText_(values[row][0]);
    if (closingNo && !index[closingNo]) {
      index[closingNo] = {
        rowNumber: row + 1,
        status: toCollectionMeshText_(values[row][1])
      };
    }
  }
  return index;
}

function buildCollectionMeshLedgerRow_(step, status, destinationRow, reason) {
  return [
    step.closingNo,
    status,
    new Date(),
    step.runId,
    step.batchId,
    step.customerId,
    step.customerName,
    step.stepType,
    step.invoiceNo,
    step.receiptNo,
    step.reportDate,
    step.journal || '',
    destinationRow || '',
    reason || ''
  ];
}

function findCollectionMeshDestinationRow_(sheet) {
  const cfg = COLLECTION_MESH_CFG;
  const lastRow = Math.max(sheet.getLastRow(), cfg.startRow - 1);
  if (lastRow < cfg.startRow) return cfg.startRow;
  const values = sheet
    .getRange(cfg.startRow, 1, lastRow - cfg.startRow + 1, cfg.destinationWidth)
    .getDisplayValues();
  for (let index = values.length - 1; index >= 0; index--) {
    if (values[index].some(function(value) { return toCollectionMeshText_(value); })) {
      return cfg.startRow + index + 1;
    }
  }
  return cfg.startRow;
}

function toCollectionMeshText_(value) {
  return value == null ? '' : String(value).trim();
}
