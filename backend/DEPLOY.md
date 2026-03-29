# AI or Not? — Backend Deployment Guide

## Overview

The backend is a Google Apps Script web app backed by a Google Sheet. It provides a REST API for recording game sessions and serving aggregate statistics. Zero infrastructure cost, zero server maintenance.

---

## Step-by-Step Setup

### 1. Create the Google Sheet

1. Go to [Google Sheets](https://sheets.google.com) and create a new blank spreadsheet.
2. Name it something recognizable, e.g., `AI or Not — Game Data`.

### 2. Open the Apps Script Editor

1. In the spreadsheet, go to **Extensions > Apps Script**.
2. This opens the Apps Script editor in a new tab.

### 3. Add the Script Files

1. In the Apps Script editor, replace the contents of `Code.gs` with the contents of `apps-script.gs` from this directory.
2. Click **+** next to "Files" in the sidebar and choose **Script**. Name it `export-jsonl`. Paste the contents of `export-jsonl.gs`.

### 4. Run `initializeSheets()`

1. In the editor, select `initializeSheets` from the function dropdown (top toolbar).
2. Click **Run**.
3. Google will ask you to authorize the script — grant permissions. This is safe; the script only accesses its own spreadsheet and your Google Drive (for exports).
4. Check your spreadsheet: you should see three sheets — **Sessions**, **ItemStats**, **ScoreDistribution** — with headers and pre-populated score rows (0-10).

### 5. Deploy as Web App

1. Click **Deploy > New deployment**.
2. Click the gear icon next to "Select type" and choose **Web app**.
3. Set:
   - **Description**: `AI or Not API v1` (or any label you want)
   - **Execute as**: `Me`
   - **Who has access**: `Anyone`
4. Click **Deploy**.
5. Copy the **Web app URL**. It looks like:
   ```
   https://script.google.com/macros/s/AKfycb.../exec
   ```

### 6. Configure the Frontend

Open `config.js` in the repo root and set:

```js
APPS_SCRIPT_URL: "https://script.google.com/macros/s/AKfycb.../exec"
```

The frontend uses this URL for both POST (submitting results) and GET (loading stats). When the URL is empty, the frontend operates in offline mode.

---

## Testing the Endpoint

### Test GET (fetch aggregate stats)

```bash
curl -L "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec"
```

Expected response (empty database):

```json
{"total_sessions":0,"item_stats":[],"score_distribution":[{"score":0,"count":0},{"score":1,"count":0},...]}
```

The `-L` flag is required because Apps Script redirects on first request.

### Test POST (submit a session)

```bash
curl -L -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-001",
    "timestamp": "2026-03-29T12:00:00Z",
    "items": [
      {"item_id": "img_001", "correct": true},
      {"item_id": "img_002", "correct": false},
      {"item_id": "img_003", "correct": true}
    ],
    "score": 2,
    "total": 3
  }' \
  "https://script.google.com/macros/s/YOUR_DEPLOYMENT_ID/exec"
```

Expected response:

```json
{"total_sessions":1,"item_stats":[...],"score_distribution":[...],"status":"ok"}
```

After posting, check the spreadsheet — you should see a new row in Sessions, updated ItemStats rows, and an incremented count in ScoreDistribution.

---

## Running the JSONL Export

1. Open the Apps Script editor.
2. Select `exportSessionsToJsonl` from the function dropdown.
3. Click **Run**.
4. Check the **Execution log** (View > Execution log) for the Google Drive file URL.
5. The file is named `ai-or-not-export-YYYY-MM-DD.jsonl` and stored in your Drive root.

To schedule automatic exports:

1. In Apps Script, go to **Triggers** (clock icon in the sidebar).
2. Click **Add Trigger**.
3. Set the function to `exportSessionsToJsonl`, event source to **Time-driven**, and choose your interval (e.g., weekly).

---

## Updating the Deployed Version

After editing the script code:

1. Click **Deploy > Manage deployments**.
2. Click the pencil icon on your active deployment.
3. Change **Version** to **New version**.
4. Click **Deploy**.

The URL stays the same. The frontend does not need any changes.

**Important**: If you only click "Save" in the editor without creating a new deployment version, the live endpoint still runs the old code. You must explicitly create a new version.

---

## Troubleshooting

### "TypeError: Cannot call method 'getSheetByName' of null"

The script is not bound to a spreadsheet. Make sure you opened the Apps Script editor from the spreadsheet (Extensions > Apps Script), not from script.google.com directly.

### POST returns HTML instead of JSON

You are hitting the wrong URL. Make sure you are using the `/exec` URL from the deployment, not the `/dev` URL. Also ensure you are following redirects (`curl -L`).

### "Exception: Lock timeout"

Multiple simultaneous writes exceeded the 10-second lock wait. This is rare at expected scale. If it happens frequently, the game has exceeded the intended use case for Google Sheets as a backend.

### CORS errors in the browser

Apps Script web apps deployed with "Anyone" access automatically include CORS headers. If you see CORS errors:
- Verify the deployment access is set to **Anyone** (not "Anyone with Google account").
- Verify you are using the `/exec` URL.
- Some browser extensions can interfere with CORS — test in an incognito window.

### Changes not appearing after code edit

You saved the script but did not create a new deployment version. See "Updating the Deployed Version" above.

### ScoreDistribution has wrong number of rows

If you changed `ITEMS_PER_SESSION` in the frontend config, you need to add or remove rows in the ScoreDistribution sheet to match. The `initializeSheets()` function creates rows 0 through 10. If your game uses a different number of items per session, manually adjust the sheet or modify `MAX_SCORE` in the script and re-run `initializeSheets()` (it will not overwrite existing rows, so delete the sheet first if you need to regenerate it).
