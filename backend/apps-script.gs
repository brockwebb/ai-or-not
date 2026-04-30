/**
 * AI or Not? — Google Apps Script Backend
 *
 * REST API for the AI or Not? game. Handles session result storage,
 * per-item accuracy tracking, and score distribution aggregation.
 *
 * Sheets schema:
 *   Sessions:          session_id | timestamp | items_json | score | total | rating | feedback | status | started_at
 *   ItemEvents:        event_id | session_id | timestamp | event_type | item_index | item_id | correct | guess_ai | reason
 *   ItemStats:         item_id | times_shown | times_correct | accuracy
 *   ScoreDistribution: score | count   (rows 0-10, pre-populated)
 *
 * Deploy as: Web app, Execute as Me, Access Anyone.
 * See DEPLOY.md for full instructions.
 */

// ---------------------------------------------------------------------------
// Configuration — keep tunables out of logic
// ---------------------------------------------------------------------------

var SHEET_SESSIONS           = "Sessions";
var SHEET_ITEM_STATS         = "ItemStats";
var SHEET_SCORE_DISTRIBUTION = "ScoreDistribution";
var SHEET_ITEM_EVENTS        = "ItemEvents";

var SESSIONS_HEADERS          = ["session_id", "timestamp", "items_json", "score", "total", "rating", "feedback", "status", "started_at"];
var ITEM_STATS_HEADERS        = ["item_id", "times_shown", "times_correct", "accuracy"];
var SCORE_DISTRIBUTION_HEADERS = ["score", "count"];
var ITEM_EVENTS_HEADERS       = ["event_id", "session_id", "timestamp", "event_type", "item_index", "item_id", "correct", "guess_ai", "reason"];

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

  // Payload size cap — reasons can add up to ~5KB; 25KB is generous ceiling
  if (e.postData.contents.length > 25000) {
    return _corsResponse({ status: "error", message: "Payload too large." });
  }

  var payload;
  try {
    payload = JSON.parse(e.postData.contents);
  } catch (err) {
    return _corsResponse({ status: "error", message: "Invalid JSON: " + err.message });
  }

  // Branch: feedback-only update (separate POST after game completion)
  if (payload.kind === "feedback") {
    return _handleFeedbackUpdate(payload);
  }

  // Branch: session heartbeats — fire-and-forget telemetry
  if (payload.kind === "session_start") {
    return _handleSessionStart(payload);
  }
  if (payload.kind === "item_answered") {
    return _handleItemAnswered(payload);
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
    // reason is optional — accept missing, null, or string ≤500 chars
    if (item.reason !== undefined && item.reason !== null) {
      if (typeof item.reason !== 'string') {
        return _corsResponse({ status: "error", message: "reason must be a string at index " + i + "." });
      }
      if (item.reason.length > 500) {
        return _corsResponse({ status: "error", message: "reason too long at index " + i + "." });
      }
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

  // rating: optional, integer 1-5 if provided
  var rating = null;
  if (payload.rating !== undefined && payload.rating !== null) {
    rating = Number(payload.rating);
    if (!Number.isInteger(rating) || rating < 1 || rating > 5) {
      return _corsResponse({ status: "error", message: "rating must be an integer 1-5 if provided." });
    }
  }

  // feedback: optional, string ≤500 chars if provided
  var feedback = "";
  if (payload.feedback !== undefined && payload.feedback !== null) {
    if (typeof payload.feedback !== 'string') {
      return _corsResponse({ status: "error", message: "feedback must be a string if provided." });
    }
    if (payload.feedback.length > 500) {
      return _corsResponse({ status: "error", message: "feedback too long." });
    }
    feedback = payload.feedback;
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
    var sessionsSheet = ss.getSheetByName(SHEET_SESSIONS);
    var lastRow = sessionsSheet.getLastRow();

    // Look up session_id to determine UPDATE-or-APPEND path.
    // If a "started" row exists (heartbeat path): update it to complete.
    // If a "complete" row exists: reject as duplicate.
    // If no row exists (heartbeats failed): append fresh row (backwards compat).
    var existingRow = -1;
    var existingStatus = null;
    if (lastRow > 0) {
      var existingData = sessionsSheet.getRange(1, 1, lastRow, SESSIONS_HEADERS.length).getValues();
      var statusIdx = _sessionsCol("status") - 1; // zero-based for array access
      for (var r = 0; r < existingData.length; r++) {
        if (String(existingData[r][0]) === String(payload.session_id)) {
          existingRow = r + 1; // 1-based sheet row
          existingStatus = String(existingData[r][statusIdx]);
          break;
        }
      }
    }

    if (existingStatus === "complete") {
      lock.releaseLock();
      return _corsResponse({ status: "error", message: "Duplicate session_id." });
    }

    if (existingRow !== -1) {
      // Heartbeat path: row exists with status="started" — update in place
      sessionsSheet.getRange(existingRow, _sessionsCol("timestamp")).setValue(String(payload.timestamp));
      sessionsSheet.getRange(existingRow, _sessionsCol("items_json")).setValue(JSON.stringify(payload.items));
      sessionsSheet.getRange(existingRow, _sessionsCol("score")).setValue(score);
      sessionsSheet.getRange(existingRow, _sessionsCol("total")).setValue(total);
      sessionsSheet.getRange(existingRow, _sessionsCol("rating")).setValue(rating);
      sessionsSheet.getRange(existingRow, _sessionsCol("feedback")).setValue(feedback);
      sessionsSheet.getRange(existingRow, _sessionsCol("status")).setValue("complete");
      // started_at left untouched — preserves original session start time
    } else {
      // Fallback path: no heartbeat row — append as before (backwards compat)
      sessionsSheet.appendRow([
        String(payload.session_id),
        String(payload.timestamp),
        JSON.stringify(payload.items),
        score,
        total,
        rating,     // null if not provided
        feedback,   // empty string if not provided
        "complete", // status
        ""          // started_at (empty — heartbeat never fired)
      ]);
    }

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
// Heartbeat handlers
// ---------------------------------------------------------------------------

/**
 * Handle kind:"session_start" — creates a "started" row in Sessions
 * and a session_start event in ItemEvents. Idempotent: silently no-ops
 * if this session_id already exists (protects against network retries).
 */
function _handleSessionStart(payload) {
  if (typeof payload.session_id !== 'string' || payload.session_id.length > 64 ||
      !/^[a-zA-Z0-9_-]+$/.test(payload.session_id)) {
    return _corsResponse({ status: "error", message: "Invalid session_id format." });
  }
  if (!payload.started_at || typeof payload.started_at !== 'string' || payload.started_at.length > 32) {
    return _corsResponse({ status: "error", message: "started_at must be an ISO 8601 string ≤32 chars." });
  }
  if (!payload.event_id || typeof payload.event_id !== 'string' || payload.event_id.length > 64 ||
      !/^[a-zA-Z0-9_-]+$/.test(payload.event_id)) {
    return _corsResponse({ status: "error", message: "Invalid event_id format." });
  }

  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch (err) {
    return _corsResponse({ status: "error", message: "Server busy. Try again." });
  }

  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sessions = ss.getSheetByName(SHEET_SESSIONS);

    // Idempotency check — don't create duplicate started rows
    var lastRow = sessions.getLastRow();
    if (lastRow > 0) {
      var ids = sessions.getRange(1, 1, lastRow, 1).getValues();
      for (var r = 0; r < ids.length; r++) {
        if (String(ids[r][0]) === String(payload.session_id)) {
          return _corsResponse({ status: "ok" }); // already exists, silently succeed
        }
      }
    }

    // Create a "started" row — score/items/etc. intentionally empty
    sessions.appendRow([
      String(payload.session_id),
      String(payload.started_at), // timestamp = start time
      "[]",     // items_json placeholder
      "",       // score — empty, not 0, to distinguish from a real 0 score
      "",       // total
      null,     // rating
      "",       // feedback
      "started", // status
      String(payload.started_at)  // started_at
    ]);

    // Also log to ItemEvents
    ss.getSheetByName(SHEET_ITEM_EVENTS).appendRow([
      String(payload.event_id),
      String(payload.session_id),
      String(payload.started_at),
      "session_start",
      null, null, null, null, "" // item-specific columns empty
    ]);
  } finally {
    lock.releaseLock();
  }

  return _corsResponse({ status: "ok" });
}

/**
 * Handle kind:"item_answered" — appends a single row to ItemEvents.
 * Does NOT touch the Sessions sheet.
 */
function _handleItemAnswered(payload) {
  if (typeof payload.session_id !== 'string' || payload.session_id.length > 64 ||
      !/^[a-zA-Z0-9_-]+$/.test(payload.session_id)) {
    return _corsResponse({ status: "error", message: "Invalid session_id format." });
  }
  if (!payload.event_id || typeof payload.event_id !== 'string' || payload.event_id.length > 64 ||
      !/^[a-zA-Z0-9_-]+$/.test(payload.event_id)) {
    return _corsResponse({ status: "error", message: "Invalid event_id format." });
  }
  if (!payload.timestamp || typeof payload.timestamp !== 'string' || payload.timestamp.length > 32) {
    return _corsResponse({ status: "error", message: "timestamp must be an ISO 8601 string ≤32 chars." });
  }
  var itemIndex = Number(payload.item_index);
  if (!Number.isInteger(itemIndex) || itemIndex < 1 || itemIndex > 10) {
    return _corsResponse({ status: "error", message: "item_index must be an integer 1–10." });
  }
  if (!payload.item_id || !/^(img|vid)-\d{3}$/.test(String(payload.item_id))) {
    return _corsResponse({ status: "error", message: "Invalid item_id format." });
  }
  if (typeof payload.correct !== 'boolean') {
    return _corsResponse({ status: "error", message: "correct must be a boolean." });
  }
  if (typeof payload.guess_ai !== 'boolean') {
    return _corsResponse({ status: "error", message: "guess_ai must be a boolean." });
  }
  var reason = "";
  if (payload.reason !== undefined && payload.reason !== null) {
    if (typeof payload.reason !== 'string' || payload.reason.length > 500) {
      return _corsResponse({ status: "error", message: "reason must be a string ≤500 chars." });
    }
    reason = payload.reason;
  }

  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch (err) {
    return _corsResponse({ status: "error", message: "Server busy. Try again." });
  }

  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    ss.getSheetByName(SHEET_ITEM_EVENTS).appendRow([
      String(payload.event_id),
      String(payload.session_id),
      String(payload.timestamp),
      "item_answered",
      itemIndex,
      String(payload.item_id),
      payload.correct,
      payload.guess_ai,
      reason
    ]);
  } finally {
    lock.releaseLock();
  }

  return _corsResponse({ status: "ok" });
}

// ---------------------------------------------------------------------------
// Feedback-only update handler
// ---------------------------------------------------------------------------

/**
 * Handle a feedback-only POST (kind: "feedback").
 * Finds the session row by session_id and writes rating + feedback columns.
 */
function _handleFeedbackUpdate(payload) {
  // Validate session_id
  if (typeof payload.session_id !== 'string' || payload.session_id.length > 64 ||
      !/^[a-zA-Z0-9_-]+$/.test(payload.session_id)) {
    return _corsResponse({ status: "error", message: "Invalid session_id format." });
  }

  // Validate rating
  var rating = null;
  if (payload.rating !== undefined && payload.rating !== null) {
    rating = Number(payload.rating);
    if (!Number.isInteger(rating) || rating < 1 || rating > 5) {
      return _corsResponse({ status: "error", message: "rating must be an integer 1-5 if provided." });
    }
  }

  // Validate feedback
  var feedback = "";
  if (payload.feedback !== undefined && payload.feedback !== null) {
    if (typeof payload.feedback !== 'string') {
      return _corsResponse({ status: "error", message: "feedback must be a string if provided." });
    }
    if (payload.feedback.length > 500) {
      return _corsResponse({ status: "error", message: "feedback too long." });
    }
    feedback = payload.feedback;
  }

  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (err) {
    return _corsResponse({ status: "error", message: "Server busy. Try again." });
  }

  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(SHEET_SESSIONS);
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) {
      return _corsResponse({ status: "error", message: "Session not found." });
    }
    var ids = sheet.getRange(1, 1, lastRow, 1).getValues();
    var targetRow = -1;
    for (var r = 0; r < ids.length; r++) {
      if (String(ids[r][0]) === String(payload.session_id)) {
        targetRow = r + 1; // 1-based
        break;
      }
    }
    if (targetRow === -1) {
      return _corsResponse({ status: "error", message: "Session not found." });
    }
    sheet.getRange(targetRow, _sessionsCol("rating")).setValue(rating);
    sheet.getRange(targetRow, _sessionsCol("feedback")).setValue(feedback);
  } finally {
    lock.releaseLock();
  }

  return _corsResponse({ status: "ok" });
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

  // ItemEvents — append-only per-item telemetry
  _ensureSheet(ss, SHEET_ITEM_EVENTS, ITEM_EVENTS_HEADERS);

  Logger.log("initializeSheets complete. Sheets: " +
    SHEET_SESSIONS + ", " + SHEET_ITEM_STATS + ", " + SHEET_SCORE_DISTRIBUTION + ", " + SHEET_ITEM_EVENTS);
}

/**
 * One-shot: add `rating` and `feedback` columns to an existing Sessions sheet.
 * Safe to run multiple times — checks the current header row first.
 * Run manually from the Apps Script editor after deploying the new code.
 */
function migrateSessionsSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_SESSIONS);
  var lastCol = sheet.getLastColumn();
  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];

  if (headers.indexOf("rating") === -1) {
    sheet.getRange(1, lastCol + 1).setValue("rating");
    sheet.getRange(1, lastCol + 1).setFontWeight("bold");
    lastCol++;
  }
  if (headers.indexOf("feedback") === -1) {
    sheet.getRange(1, lastCol + 1).setValue("feedback");
    sheet.getRange(1, lastCol + 1).setFontWeight("bold");
  }

  Logger.log("migrateSessionsSheet complete. Header row: " +
    sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].join(", "));
}

/**
 * One-shot v2 migration: adds `status` and `started_at` columns to Sessions,
 * backfills existing complete rows, and creates the ItemEvents sheet.
 * Safe to run multiple times.
 * Run manually from the Apps Script editor after deploying the new code.
 */
function migrateSessionsSheet_v2() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // 1. Add status and started_at columns to Sessions if missing
  var sessionsSheet = ss.getSheetByName(SHEET_SESSIONS);
  var lastCol = sessionsSheet.getLastColumn();
  var headers = sessionsSheet.getRange(1, 1, 1, lastCol).getValues()[0];

  if (headers.indexOf("status") === -1) {
    sessionsSheet.getRange(1, lastCol + 1).setValue("status");
    sessionsSheet.getRange(1, lastCol + 1).setFontWeight("bold");
    lastCol++;
  }
  if (headers.indexOf("started_at") === -1) {
    sessionsSheet.getRange(1, lastCol + 1).setValue("started_at");
    sessionsSheet.getRange(1, lastCol + 1).setFontWeight("bold");
  }

  // 2. Backfill status="complete" for all existing rows that have no status yet
  var statusCol = SESSIONS_HEADERS.indexOf("status") + 1; // 1-based
  var sessionsLastRow = sessionsSheet.getLastRow();
  if (sessionsLastRow > 1) {
    var allStatuses = sessionsSheet.getRange(2, statusCol, sessionsLastRow - 1, 1).getValues();
    for (var r = 0; r < allStatuses.length; r++) {
      if (!allStatuses[r][0]) {
        sessionsSheet.getRange(r + 2, statusCol).setValue("complete");
      }
    }
  }

  // 3. Create ItemEvents sheet if missing
  _ensureSheet(ss, SHEET_ITEM_EVENTS, ITEM_EVENTS_HEADERS);

  Logger.log("migrateSessionsSheet_v2 complete. Sessions headers: " +
    sessionsSheet.getRange(1, 1, 1, sessionsSheet.getLastColumn()).getValues()[0].join(", ") +
    ". ItemEvents sheet ensured.");
}

/**
 * Manual reconciliation entry point. Run from the Apps Script editor
 * after a deploy or on demand. Idempotent — re-running does nothing
 * once all ghost-completes are resolved.
 *
 * Logs the count of rows repaired on this call.
 */
function repairGhostCompletes() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var result = _reconcileGhostCompletes(ss);
  Logger.log("repairGhostCompletes complete. Reconciled " + result.reconciled + " row(s).");
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
 * Return the 1-based column number for a named column in the Sessions sheet.
 * Throws if the column name is not in SESSIONS_HEADERS — fail loud, not silent.
 *
 * Usage: _sessionsCol("rating")  →  6  (or whatever the current position is)
 */
function _sessionsCol(name) {
  var idx = SESSIONS_HEADERS.indexOf(name);
  if (idx === -1) {
    throw new Error("_sessionsCol: unknown column name: " + name);
  }
  return idx + 1; // 1-based for Sheets API
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
 * Reconcile ghost-complete sessions: rows with status='started' that actually
 * have exactly MAX_SCORE item_answered events in ItemEvents. These are
 * save failures where the completion POST never landed, not real dropouts.
 *
 * Flips each matching row to status='complete', reconstructs score +
 * items_json from the events, and catches aggregate sheets (ItemStats,
 * ScoreDistribution) up so the session counts the same way a normal
 * completion would.
 *
 * Called from _readAggregates on every GET so data self-heals over time.
 * Safe to call repeatedly — only touches rows that still match the strict
 * criteria after the status re-check inside the lock.
 *
 * Returns { reconciled: N } — count of rows repaired on this call.
 */
function _reconcileGhostCompletes(ss) {
  var sessionsSheet = ss.getSheetByName(SHEET_SESSIONS);
  var eventsSheet   = ss.getSheetByName(SHEET_ITEM_EVENTS);
  if (!sessionsSheet || !eventsSheet) return { reconciled: 0 };

  var sessionsLastRow = sessionsSheet.getLastRow();
  var eventsLastRow   = eventsSheet.getLastRow();
  if (sessionsLastRow < 2 || eventsLastRow < 2) return { reconciled: 0 };

  // Collect candidate rows: status='started' at time of scan.
  var statusIdx = SESSIONS_HEADERS.indexOf("status");
  var sessRows  = sessionsSheet.getRange(2, 1, sessionsLastRow - 1, SESSIONS_HEADERS.length).getValues();
  var startedRows = {}; // sid -> { rowNumber }
  for (var i = 0; i < sessRows.length; i++) {
    if (String(sessRows[i][statusIdx]) === "started") {
      startedRows[String(sessRows[i][0])] = { rowNumber: i + 2 };
    }
  }
  var startedIds = Object.keys(startedRows);
  if (startedIds.length === 0) return { reconciled: 0 };

  // Walk ItemEvents once; bucket item_answered events by session_id.
  var sidIdx     = ITEM_EVENTS_HEADERS.indexOf("session_id");
  var typeIdx    = ITEM_EVENTS_HEADERS.indexOf("event_type");
  var itemIdIdx  = ITEM_EVENTS_HEADERS.indexOf("item_id");
  var correctIdx = ITEM_EVENTS_HEADERS.indexOf("correct");
  var events     = eventsSheet.getRange(2, 1, eventsLastRow - 1, ITEM_EVENTS_HEADERS.length).getValues();

  var perSession = {}; // sid -> [ { item_id, correct }, ... ]
  for (var e = 0; e < events.length; e++) {
    if (String(events[e][typeIdx]) !== "item_answered") continue;
    var sid = String(events[e][sidIdx]);
    if (!startedRows[sid]) continue;
    if (!perSession[sid]) perSession[sid] = [];
    perSession[sid].push({
      item_id: String(events[e][itemIdIdx]),
      correct: events[e][correctIdx] === true ||
               String(events[e][correctIdx]).toLowerCase() === "true"
    });
  }

  // Acquire the same lock the POST paths use. Prevents a completion POST
  // arriving mid-reconcile from double-counting in ItemStats/ScoreDistribution.
  var lock = LockService.getScriptLock();
  try { lock.waitLock(10000); } catch (err) { return { reconciled: 0 }; }

  var reconciled = 0;
  try {
    for (var j = 0; j < startedIds.length; j++) {
      var sidJ  = startedIds[j];
      var items = perSession[sidJ];
      if (!items || items.length !== MAX_SCORE) continue;

      var rowNum = startedRows[sidJ].rowNumber;

      // Double-count guard: re-read status after lock acquired.
      // If a completion POST flipped this row while we were waiting, bail —
      // ItemStats and ScoreDistribution were already updated by that path.
      var currentStatus = String(sessionsSheet.getRange(rowNum, _sessionsCol("status")).getValue());
      if (currentStatus !== "started") continue;

      var score = 0;
      for (var k = 0; k < items.length; k++) if (items[k].correct) score++;

      sessionsSheet.getRange(rowNum, _sessionsCol("items_json")).setValue(JSON.stringify(items));
      sessionsSheet.getRange(rowNum, _sessionsCol("score")).setValue(score);
      sessionsSheet.getRange(rowNum, _sessionsCol("total")).setValue(MAX_SCORE);
      sessionsSheet.getRange(rowNum, _sessionsCol("status")).setValue("complete");

      // Catch aggregate sheets up. These are NOT idempotent, which is why
      // the status re-check above is essential.
      _updateItemStats(ss, items);
      _updateScoreDistribution(ss, score);

      reconciled++;
    }
  } finally {
    lock.releaseLock();
  }

  if (reconciled > 0) {
    Logger.log("_reconcileGhostCompletes: reconciled " + reconciled + " session(s).");
  }
  return { reconciled: reconciled };
}

/**
 * Read all aggregate data from ItemStats, ScoreDistribution, Sessions,
 * and ItemEvents.
 *
 * Returns:
 *   {
 *     total_sessions,         // completed sessions (back-compat; = sessions_completed)
 *     item_stats: [...],
 *     score_distribution: [...],
 *     sessions_started,       // total population ever started (started + completed)
 *     sessions_completed,     // rows with status='complete'
 *     dropouts: [              // one record per abandoned session
 *       { session_id, items_answered, accuracy_at_quit }
 *     ]
 *   }
 *
 * Backward-compatible: existing fields unchanged; new fields added.
 */
function _readAggregates(ss) {
  // Self-heal first: promote any ghost-complete sessions (status='started'
  // rows that actually have 10 item_answered events) to status='complete'
  // so every aggregate below reflects accurate session counts and scores.
  _reconcileGhostCompletes(ss);

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

  // Sessions status counts (started vs complete)
  var sessionsSheet = ss.getSheetByName(SHEET_SESSIONS);
  var sessionsLastRow = sessionsSheet ? sessionsSheet.getLastRow() : 0;
  var sessions_started_only    = 0;  // status == 'started', still in flight / abandoned
  var sessions_completed_count = 0;  // status == 'complete'
  var startedSessionIds = {};        // session_id -> true for status='started' rows

  if (sessionsLastRow > 1) {
    var statusCol = SESSIONS_HEADERS.indexOf("status") + 1; // 1-based
    var rows = sessionsSheet.getRange(2, 1, sessionsLastRow - 1, SESSIONS_HEADERS.length).getValues();
    for (var i = 0; i < rows.length; i++) {
      var s = String(rows[i][statusCol - 1]);
      if (s === "started") {
        sessions_started_only++;
        startedSessionIds[String(rows[i][0])] = true;
      } else if (s === "complete") {
        sessions_completed_count++;
      }
    }
  }

  // Aggregate item_answered events per session for dropout classification.
  // Only sessions flagged status='started' in Sessions are candidates.
  var dropouts = [];
  var eventsSheet = ss.getSheetByName(SHEET_ITEM_EVENTS);
  var eventsLastRow = eventsSheet ? eventsSheet.getLastRow() : 0;
  if (eventsLastRow > 1 && sessions_started_only > 0) {
    var sessionIdIdx = ITEM_EVENTS_HEADERS.indexOf("session_id");
    var eventTypeIdx = ITEM_EVENTS_HEADERS.indexOf("event_type");
    var correctIdx   = ITEM_EVENTS_HEADERS.indexOf("correct");

    var events = eventsSheet.getRange(2, 1, eventsLastRow - 1, ITEM_EVENTS_HEADERS.length).getValues();
    var perSession = {}; // sid -> { answered, correct }
    for (var e = 0; e < events.length; e++) {
      var row = events[e];
      if (String(row[eventTypeIdx]) !== "item_answered") continue;
      var sid = String(row[sessionIdIdx]);
      if (!startedSessionIds[sid]) continue; // ignore events for completed sessions
      if (!perSession[sid]) perSession[sid] = { answered: 0, correct: 0 };
      perSession[sid].answered++;
      var c = row[correctIdx];
      if (c === true || String(c).toLowerCase() === "true") {
        perSession[sid].correct++;
      }
    }
    for (var sid2 in perSession) {
      if (!perSession.hasOwnProperty(sid2)) continue;
      var rec = perSession[sid2];
      if (rec.answered === 0) continue;
      dropouts.push({
        session_id:       sid2,
        items_answered:   rec.answered,
        accuracy_at_quit: rec.correct / rec.answered
      });
    }
  }

  return {
    total_sessions:     totalSessions,
    item_stats:         itemStats,
    score_distribution: scoreDist,
    sessions_started:   sessions_started_only + sessions_completed_count,
    sessions_completed: sessions_completed_count,
    dropouts:           dropouts
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
