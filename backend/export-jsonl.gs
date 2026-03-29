/**
 * AI or Not? — JSONL Export
 *
 * Reads all session rows from the "Sessions" sheet and writes them
 * to a JSONL file on Google Drive. One JSON object per line.
 *
 * Run manually from the Apps Script editor or attach to a trigger
 * for periodic exports.
 *
 * Output filename: ai-or-not-export-YYYY-MM-DD.jsonl
 */

var EXPORT_SHEET_NAME = "Sessions";

/**
 * Export all sessions to a JSONL file on Google Drive.
 * Logs the file URL for easy access.
 */
function exportSessionsToJsonl() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(EXPORT_SHEET_NAME);

  if (!sheet) {
    Logger.log("ERROR: Sheet '" + EXPORT_SHEET_NAME + "' not found. Run initializeSheets() first.");
    return;
  }

  var data = sheet.getDataRange().getValues();
  if (data.length <= 1) {
    Logger.log("No session data to export (sheet has only headers).");
    return;
  }

  // Header row defines field names
  var headers = data[0];
  var lines = [];

  for (var r = 1; r < data.length; r++) {
    var row = data[r];
    var record = {};

    for (var c = 0; c < headers.length; c++) {
      var key = String(headers[c]).trim();
      var val = row[c];

      // Parse items_json back into an object so the JSONL is fully structured
      if (key === "items_json" && typeof val === "string") {
        try {
          record["items"] = JSON.parse(val);
        } catch (e) {
          // If parsing fails, store the raw string
          record["items_json_raw"] = val;
        }
      } else {
        record[key] = val;
      }
    }

    lines.push(JSON.stringify(record));
  }

  var jsonlContent = lines.join("\n");
  var today = _formatDate(new Date());
  var filename = "ai-or-not-export-" + today + ".jsonl";

  var file = DriveApp.createFile(filename, jsonlContent, "application/x-jsonlines");
  var url = file.getUrl();

  Logger.log("Export complete.");
  Logger.log("  Rows exported: " + lines.length);
  Logger.log("  Filename:      " + filename);
  Logger.log("  Drive URL:     " + url);

  return url;
}

/**
 * Format a Date as YYYY-MM-DD.
 */
function _formatDate(d) {
  var year  = d.getFullYear();
  var month = ("0" + (d.getMonth() + 1)).slice(-2);
  var day   = ("0" + d.getDate()).slice(-2);
  return year + "-" + month + "-" + day;
}
