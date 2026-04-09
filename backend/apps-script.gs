/**
 * AI or Not? — Google Apps Script Backend
 *
 * REST API for the AI or Not? game. Handles session result storage,
 * per-item accuracy tracking, and score distribution aggregation.
 *
 * Sheets schema:
 *   Sessions:          session_id | timestamp | items_json | score | total
 *   ItemStats:         item_id | times_shown | times_correct | accuracy
 *   ScoreDistribution: score | count   (rows 0-10, pre-populated)
 *
 * Deploy as: Web app, Execute as Me, Access Anyone.
 * See DEPLOY.md for full instructions.
 */

// ---------------------------------------------------------------------------
// Configuration — keep tunables out of logic
// ---------------------------------------------------------------------------

var SHEET_SESSIONS          = "Sessions";
var SHEET_ITEM_STATS        = "ItemStats";
var SHEET_SCORE_DISTRIBUTION = "ScoreDistribution";

var SESSIONS_HEADERS          = ["session_id", "timestamp", "items_json", "score", "total"];
var ITEM_STATS_HEADERS        = ["item_id", "times_shown", "times_correct", "accuracy"];
var SCORE_DISTRIBUTION_HEADERS = ["score", "count"];

var MAX_SCORE = 10; // matches CONFIG.ITEMS_PER_SESSION in the frontend

// ---------------------------------------------------------------------------
// HTTP entry points
// ---------------------------------------------------------------------------

/**
 * Handle POST requests — record a completed game session.
 *
 * Expected JSON body:
 *   { session_id, timestamp, items: [{item_id, correct}], score, total }
 *
 * Returns current aggregate stats so the frontend can render the results
 * screen without a separate GET.
 */
function doPost(e) {
  // CORS preflight may arrive as POST with empty body in some browsers
  if (!e || !e.postData || !e.postData.contents) {
    return _corsResponse({ status: "error", message: "No POST body received." });
  }

  // Payload size cap — reject obviously oversized requests (legit session ~1-2KB)
  if (e.postData.contents.length > 10000) {
    return _corsResponse({ status: "error", message: "Payload too large." });
  }

  var payload;
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (err) {
    return _corsResponse({ status: "error", message: "Invalid JSON: " + err.message });
  }

  // --- Validate required fields ---
  var missing = _missingFields(payload, ["session_id", "timestamp", "items", "score", "total"]);
  if (missing.length > 0) {
    return _corsResponse({ status: "error", message: "Missing fields: " + missing.join(", ") });
  }

  // Validate session_id format — alphanumeric, hyphens, underscores, max 64 chars
  if (typeof payload.session_id !== 'string' || payload.session_id.length > 64 || !/^[a-zA-Z0-9_-]+$/.test(payload.session_id)) {
    return _corsResponse({ status: "error", message: "Invalid session_id format." });
  }

  if (!Array.isArray(payload.items) || payload.items.length === 0) {
    return _corsResponse({ status: "error", message: "items must be a non-empty array." });
  }

  // Validate each item has required sub-fields and a well-formed item_id
  for (var i = 0; i < payload.items.length; i++) {
    var item = payload.items[i];
    if (item.item_id === undefined || item.correct === undefined) {
      return _corsResponse({
        status: "error",
        message: "Each item must have item_id and correct. Problem at index " + i + "."
      });
    }
    if (!/^(img|vid)-\d{3}$/.test(String(item.item_id))) {
      return _corsResponse({
        status: "error",
        message: "Invalid item_id format: " + item.item_id
      });
    }
  }

  // Items array length must exactly match total
  if (payload.items.length !== Number(payload.total)) {
    return _corsResponse({ status: "error", message: "items array length must equal total." });
  }

  // total must equal MAX_SCORE (sessions are always exactly 10 items)
  if (Number(payload.total) !== MAX_SCORE) {
    return _corsResponse({ status: "error", message: "total must equal " + MAX_SCORE + "." });
  }

  // Validate score is a reasonable number
  var score = Number(payload.score);
  var total = Number(payload.total);
  if (isNaN(score) || isNaN(total) || score < 0 || score > total) {
    return _corsResponse({ status: "error", message: "score must be a number between 0 and total." });
  }

  // --- Write data under lock to prevent race conditions ---
  var lock = LockService.getScriptLock();
  try {
    // Wait up to 10 seconds for the lock
    lock.waitLock(10000);
  } catch (err) {
    return _corsResponse({ status: "error", message: "Server busy. Try again." });
  }

  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    // Reject duplicate session_ids — prevents replayed or double-submitted sessions
    var sessionsSheet = ss.getSheetByName(SHEET_SESSIONS);
    var lastRow = sessionsSheet.getLastRow();
    if (lastRow > 0) {
      var existingIds = sessionsSheet.getRange(1, 1, lastRow, 1).getValues();
      for (var r = 0; r < existingIds.length; r++) {
        if (String(existingIds[r][0]) === String(payload.session_id)) {
          lock.releaseLock();
          return _corsResponse({ status: "error", message: "Duplicate session_id." });
        }
      }
    }

    // 1. Append session row
    sessionsSheet.appendRow([
      String(payload.session_id),
      String(payload.timestamp),
      JSON.stringify(payload.items),
      score,
      total
    ]);

    // 2. Update per-item stats
    _updateItemStats(ss, payload.items);

    // 3. Update score distribution
    _updateScoreDistribution(ss, score);

  } finally {
    lock.releaseLock();
  }

  // Return current aggregates so frontend can render results immediately
  var stats = _readAggregates(ss);
  stats.status = "ok";
  return _corsResponse(stats);
}

/**
 * Handle GET requests — return current aggregate stats.
 *
 * No parameters required.
 */
function doGet(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var stats = _readAggregates(ss);
  return _corsResponse(stats);
}

// ---------------------------------------------------------------------------
// Initialization — run once after creating the Google Sheet
// ---------------------------------------------------------------------------

/**
 * Create the three required sheets with proper headers.
 * Safe to run multiple times — skips sheets that already exist.
 */
function initializeSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // Sessions
  _ensureSheet(ss, SHEET_SESSIONS, SESSIONS_HEADERS);

  // ItemStats
  _ensureSheet(ss, SHEET_ITEM_STATS, ITEM_STATS_HEADERS);

  // ScoreDistribution — pre-populate rows 0 through MAX_SCORE
  var sdSheet = _ensureSheet(ss, SHEET_SCORE_DISTRIBUTION, SCORE_DISTRIBUTION_HEADERS);
  if (sdSheet.getLastRow() <= 1) {
    // Only populate if the sheet is empty (just headers)
    for (var s = 0; s <= MAX_SCORE; s++) {
      sdSheet.appendRow([s, 0]);
    }
  }

  Logger.log("initializeSheets complete. Sheets: " +
    SHEET_SESSIONS + ", " + SHEET_ITEM_STATS + ", " + SHEET_SCORE_DISTRIBUTION);
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Return an array of field names missing from obj.
 */
function _missingFields(obj, required) {
  var missing = [];
  for (var i = 0; i < required.length; i++) {
    if (obj[required[i]] === undefined || obj[required[i]] === null) {
      missing.push(required[i]);
    }
  }
  return missing;
}

/**
 * Ensure a sheet exists with the given name and headers. Returns the sheet.
 */
function _ensureSheet(ss, name, headers) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow(headers);
    // Bold the header row for readability
    sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold");
  }
  return sheet;
}

/**
 * Update ItemStats sheet for each item in the session.
 * Looks up each item_id; creates a new row if not found.
 */
function _updateItemStats(ss, items) {
  var sheet = ss.getSheetByName(SHEET_ITEM_STATS);
  var data = sheet.getDataRange().getValues();

  // Build a lookup: item_id -> row index (1-based, skipping header)
  var lookup = {};
  for (var r = 1; r < data.length; r++) {
    lookup[String(data[r][0])] = r + 1; // +1 because getDataRange is 1-indexed in sheet
  }

  for (var i = 0; i < items.length; i++) {
    var itemId = String(items[i].item_id);
    var isCorrect = items[i].correct === true;

    if (lookup[itemId]) {
      // Existing row — update in place
      var row = lookup[itemId];
      var timesShown   = sheet.getRange(row, 2).getValue() + 1;
      var timesCorrect = sheet.getRange(row, 3).getValue() + (isCorrect ? 1 : 0);
      var accuracy     = timesCorrect / timesShown;

      sheet.getRange(row, 2).setValue(timesShown);
      sheet.getRange(row, 3).setValue(timesCorrect);
      sheet.getRange(row, 4).setValue(accuracy);
    } else {
      // New item — append row
      var newTimesShown   = 1;
      var newTimesCorrect = isCorrect ? 1 : 0;
      var newAccuracy     = newTimesCorrect / newTimesShown;
      sheet.appendRow([itemId, newTimesShown, newTimesCorrect, newAccuracy]);

      // Update lookup so duplicate items in the same session work correctly
      lookup[itemId] = sheet.getLastRow();
    }
  }
}

/**
 * Increment the count for the given score in ScoreDistribution.
 * Score row is at index score+2 (row 1 = header, row 2 = score 0, etc.)
 */
function _updateScoreDistribution(ss, score) {
  var sheet = ss.getSheetByName(SHEET_SCORE_DISTRIBUTION);
  // Clamp score to valid range
  var s = Math.max(0, Math.min(MAX_SCORE, Math.round(score)));
  var row = s + 2; // header is row 1, score 0 is row 2
  var currentCount = sheet.getRange(row, 2).getValue();
  sheet.getRange(row, 2).setValue(currentCount + 1);
}

/**
 * Read all aggregate data from ItemStats and ScoreDistribution.
 * Returns { total_sessions, item_stats: [...], score_distribution: [...] }
 */
function _readAggregates(ss) {
  // Item stats
  var itemSheet = ss.getSheetByName(SHEET_ITEM_STATS);
  var itemData = itemSheet.getDataRange().getValues();
  var itemStats = [];
  for (var r = 1; r < itemData.length; r++) {
    itemStats.push({
      item_id:       itemData[r][0],
      times_shown:   itemData[r][1],
      times_correct: itemData[r][2],
      accuracy:      itemData[r][3]
    });
  }

  // Score distribution
  var sdSheet = ss.getSheetByName(SHEET_SCORE_DISTRIBUTION);
  var sdData = sdSheet.getDataRange().getValues();
  var scoreDist = [];
  var totalSessions = 0;
  for (var r = 1; r < sdData.length; r++) {
    var count = Number(sdData[r][1]) || 0;
    scoreDist.push({
      score: sdData[r][0],
      count: count
    });
    totalSessions += count;
  }

  return {
    total_sessions:     totalSessions,
    item_stats:         itemStats,
    score_distribution: scoreDist
  };
}

/**
 * Build a CORS-enabled JSON response.
 * Apps Script doGet/doPost must return a ContentService TextOutput.
 */
function _corsResponse(data) {
  var output = ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
  // Note: Apps Script web apps do not support custom response headers directly.
  // CORS is handled by Google's infrastructure — Apps Script web app endpoints
  // automatically include Access-Control-Allow-Origin: * when deployed as
  // "Anyone" access. The _corsResponse wrapper ensures consistent JSON output.
  return output;
}
