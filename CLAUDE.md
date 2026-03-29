# AI or Not? — Project Context for AI Assistants

## What This Is

An open-source web game for youth education (Scouts, Census bring-your-kid-to-work day, general public) where players view images/videos and guess whether they are AI-generated or real. Designed to teach deepfake literacy, data science concepts, and critical thinking.

Covers Scouting America AI Merit Badge requirements 2d ("AI or Not?" scenario game) and requirement 5 (Deepfakes). But the game stands alone — it is not limited to scout use.

## Architecture

### Frontend (GitHub Pages)
- **Single-file static web app** — HTML/CSS/JS, no frameworks, no React, no build step
- Pulls 10 random items per session from `content.json`
- Per-item: player guesses AI or Not, optional free-text reasoning field
- POSTs session results to Google Apps Script backend
- GETs aggregate stats back for end-of-session results screen
- End screen shows: score, percentile vs. all players, per-item difficulty heatmap, accuracy distribution

### Backend (Google Apps Script + Google Sheets)
- Apps Script serves as REST API (POST to write results, GET to read aggregates)
- Sheet 1: raw session data (append-only)
- Sheet 2: aggregate item stats (updated on each POST)
- Zero infrastructure, zero cost, unlimited scale for this use case

### Content Library (`content.json`)
- JSON file in repo root — the single source of truth for game content
- Each item: `id`, `url`, `media_type` (image|video), `is_ai` (boolean), `source`, `attribution`, `license`, `explanation`, `category`, `generation_method`, `prior_difficulty` (curator's Bayesian prior, 0.0-1.0), `tags`
- All content is curated and reviewed by project maintainer before merge
- Content must be safe for children — no exceptions
- PRs welcome to add items; all submissions reviewed manually

### Data Collection
- JSONL format, append-only, one line per session
- Fields: session_id, timestamp, items_shown (array of item IDs), guesses (array of booleans), correct (array of booleans), reasoning (array of strings), score, total_items
- Anonymous — no PII collected
- Exported periodically from Google Sheet for analysis

### Analysis Workbench (`analysis/`)
- Offline Python scripts, not user-facing
- Beta-Binomial Bayesian difficulty updating (prior = curator score, updated from observations)
- Item Response Theory (IRT) 1PL model for simultaneous item difficulty / player ability estimation
- Drift detection: rolling accuracy over time to measure improving AI generation quality
- Prior-vs-observed calibration scatter (measures curator's beginner's-mind accuracy)
- LLM batch processing of reasoning text for strategy clustering
- All analysis reads from JSONL exports

## Key Design Decisions

- **AD-001**: No frameworks. Static HTML/CSS/JS only. Rationale: must be hostable on GitHub Pages, forkable by anyone, zero build step. Kids and scout leaders should be able to fork and deploy in minutes.
- **AD-002**: Google Sheets as database via Apps Script. Rationale: free, zero-maintenance, sufficient for expected scale, data exportable as CSV/JSONL. Not a production database, but this isn't a production app.
- **AD-003**: Bayesian priors on difficulty use curator's informative prior, not a weak prior. Rationale: measuring the gap between prior and observed IS a research goal (curator calibration / beginner's mind test).
- **AD-004**: Content safety is enforced at the content library level, not the application level. All items are reviewed before merge. The app renders only what's in `content.json`.
- **AD-005**: JSONL for time-series data export. Append-only, timestamped, natural format for drift analysis.

## Tech Stack

- HTML/CSS/JS (frontend)
- Google Apps Script (backend API)
- Google Sheets (data store)
- Python (analysis scripts)
- GitHub Pages (hosting)

## Audiences

1. **Primary**: Scouts (ages 10-17) working on AI Merit Badge
2. **Secondary**: Census Bureau bring-your-kid-to-work day participants (ages ~6-17)
3. **Tertiary**: General public, other scout troops, educators

## Content Sourcing

- Curator's personal collection (Twitter/X saves, various AI demos)
- Open-source datasets (Kaggle: CIFAKE, AI Generated vs Real Images)
- Existing games for reference: sightengine.com/ai-or-not, Leon Furze's deepfake game, Hany Farid's Berkeley quiz
- All content must have attribution and respect source licenses

## What NOT To Do

- Do not introduce npm, webpack, vite, or any build toolchain
- Do not use React, Vue, Svelte, or any frontend framework
- Do not require a local server to develop or test (file:// should work for dev, GitHub Pages for prod)
- Do not collect PII — no names, emails, IP addresses stored
- Do not hardcode API endpoints — use config
- Do not over-engineer the MVP — the game frontend is a web page, not a SPA
