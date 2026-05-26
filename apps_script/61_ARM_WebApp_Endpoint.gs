/**
 * ARM Collection import WebApp endpoint.
 *
 * Expected POST body:
 * {
 *   "token": "<shared secret matching ScriptProperties.ARM_WEBAPP_TOKEN>",
 *   "rows": [
 *     [
 *       "customer_name",
 *       "invoice_date",
 *       "invoice_number",
 *       "closing_number",
 *       "sales",
 *       "receivable_amount",
 *       "unpaid_amount"
 *     ]
 *   ]
 * }
 *
 * Success response:
 * {"ok": true, "rows": 1, "sheetName": "Collection", "writeRange": "A3:G3"}
 *
 * Error response:
 * {"ok": false, "error": "..."}
 *
 * This endpoint rewrites only the Collection data body. Collection!B1 is
 * intentionally updated by scripts/arm_export_to_collection.py after import.
 */

var ARM_ROW_FIELDS = [
  "customer_name",
  "invoice_date",
  "invoice_number",
  "closing_number",
  "sales",
  "receivable_amount",
  "unpaid_amount"
];

var ARM_ROW_WIDTH = ARM_ROW_FIELDS.length;
var ARM_CLOSING_NUMBER_INDEX = 3;
var ARM_CLOSING_NUMBER_PATTERN = /^61\d{2}-\d{10}$/;

var ARM_WEBAPP_TOKEN_PROPERTY = "ARM_WEBAPP_TOKEN";
var ARM_COLLECTION_SPREADSHEET_ID_PROPERTY = "ARM_COLLECTION_SPREADSHEET_ID";
var ARM_COLLECTION_SHEET_NAME_PROPERTY = "ARM_COLLECTION_SHEET_NAME";
var ARM_COLLECTION_DATA_START_ROW_PROPERTY = "ARM_COLLECTION_DATA_START_ROW";
var ARM_COLLECTION_DATA_START_COLUMN_PROPERTY = "ARM_COLLECTION_DATA_START_COLUMN";
var ARM_COLLECTION_CLEAR_COLUMNS_PROPERTY = "ARM_COLLECTION_CLEAR_COLUMNS";

function doPost(e) {
  try {
    var payload = parseRequest_(e);
    validateToken_(payload.token);
    var rows = validateRows_(payload.rows);
    var writeResult = replaceCollectionRows_(rows);

    return jsonResponse_({
      ok: true,
      rows: rows.length,
      sheetName: writeResult.sheetName,
      writeRange: writeResult.writeRange
    });
  } catch (error) {
    return jsonResponse_({
      ok: false,
      error: String(error && error.message ? error.message : error)
    });
  }
}

function parseRequest_(e) {
  if (!e || !e.postData || !e.postData.contents) {
    throw new Error("Missing JSON POST body.");
  }
  try {
    return JSON.parse(e.postData.contents);
  } catch (error) {
    throw new Error("Invalid JSON POST body.");
  }
}

function validateToken_(token) {
  var expected = getRequiredScriptProperty_(ARM_WEBAPP_TOKEN_PROPERTY);
  if (!token || token !== expected) {
    throw new Error("Invalid token");
  }
}

function validateRows_(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    throw new Error("rows must be a non-empty array.");
  }

  rows.forEach(function(row, rowIndex) {
    if (!Array.isArray(row)) {
      throw new Error("row " + (rowIndex + 1) + " must be an array.");
    }
    if (row.length !== ARM_ROW_WIDTH) {
      throw new Error("row " + (rowIndex + 1) + " must have " + ARM_ROW_WIDTH + " cells.");
    }
    row.forEach(function(value, columnIndex) {
      if (typeof value !== "string") {
        throw new Error(
          "row " + (rowIndex + 1) + " field " + ARM_ROW_FIELDS[columnIndex] + " must be a string."
        );
      }
    });
    if (!ARM_CLOSING_NUMBER_PATTERN.test(row[ARM_CLOSING_NUMBER_INDEX].trim())) {
      throw new Error("row " + (rowIndex + 1) + " has invalid closing_number.");
    }
  });

  return rows;
}

function replaceCollectionRows_(rows) {
  var spreadsheetId = getOptionalScriptProperty_(ARM_COLLECTION_SPREADSHEET_ID_PROPERTY);
  var spreadsheet = spreadsheetId
    ? SpreadsheetApp.openById(spreadsheetId)
    : SpreadsheetApp.getActiveSpreadsheet();
  if (!spreadsheet) {
    throw new Error("No active spreadsheet. Set ScriptProperties.ARM_COLLECTION_SPREADSHEET_ID.");
  }

  var sheetName = getOptionalScriptProperty_(ARM_COLLECTION_SHEET_NAME_PROPERTY) || "Collection";
  var sheet = spreadsheet.getSheetByName(sheetName);
  if (!sheet) {
    throw new Error("Sheet not found: " + sheetName);
  }

  var startRow = Number(getOptionalScriptProperty_(ARM_COLLECTION_DATA_START_ROW_PROPERTY) || 3);
  var startColumn = Number(getOptionalScriptProperty_(ARM_COLLECTION_DATA_START_COLUMN_PROPERTY) || 1);
  var clearColumns = Number(getOptionalScriptProperty_(ARM_COLLECTION_CLEAR_COLUMNS_PROPERTY) || ARM_ROW_WIDTH);
  var clearRows = Math.max(sheet.getLastRow() - startRow + 1, rows.length, 1);

  sheet.getRange(startRow, startColumn, clearRows, clearColumns).clearContent();

  var writeRange = "";
  if (rows.length > 0) {
    var range = sheet.getRange(startRow, startColumn, rows.length, ARM_ROW_WIDTH);
    range.setValues(rows);
    writeRange = range.getA1Notation();
  }

  return {
    sheetName: sheetName,
    writeRange: writeRange
  };
}

function getRequiredScriptProperty_(name) {
  var value = getOptionalScriptProperty_(name);
  if (!value) {
    throw new Error("Missing ScriptProperties." + name);
  }
  return value;
}

function getOptionalScriptProperty_(name) {
  return PropertiesService.getScriptProperties().getProperty(name);
}

function jsonResponse_(body) {
  return ContentService
    .createTextOutput(JSON.stringify(body))
    .setMimeType(ContentService.MimeType.JSON);
}
