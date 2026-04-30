# `/stats/` — Live Data Station (v2)

A single-page dashboard that reads the AI or Not? backend and presents the
live game data as an instrument panel. v2 pivots from "AI-detection literacy"
to **data-collection pedagogy**: the dashboard teaches how data is gathered,
interpreted, and questioned — using AI-detection as the substrate.

Deploys to: `https://brockwebb.github.io/ai-or-not/stats/`

## Audiences & framing

- **Kids at Census bring-your-kid-to-work day** — Census is a measurement
  agency; the dashboard shows "here is us measuring something live."
- **Scouts on the AI Merit Badge** — same dashboard, Pip-Boy theme turns it
  from corporate briefing room into personal tricorder.
- **Statistically literate adults passing by** — real mean vs median split, a
  real dropout scatter, real accuracy dials. No dashboard decoration.

## Teaching moments the widgets support

- **Distribution with mean + median**: "Why are the two different? Which one
  is more honest for skewed data?"
- **REAL vs AI dials**: "Why are humans better at spotting one class than the
  other? What does this say about AI progress?"
- **Started vs Finished meter**: "Why do some people quit? Should we throw out
  their data?"
- **Dropout scatter**: "Each dot is someone who quit. Color + shape show how
  they were doing. What do YOU think made them quit — frustration or boredom?"
- **Hero LED cycle**: rotating one-liners about the data itself (plays,
  starts, dropout rate, most-missed item, overall accuracy).

## How it works

On page load and on every Refresh click:

1. GET `../content.json` — for `is_ai` ground truth.
2. GET `CONFIG.APPS_SCRIPT_URL` — backend aggregates. The v2 payload includes
   `total_sessions`, `item_stats[]`, `score_distribution[]`, plus new v2
   fields `sessions_started`, `sessions_completed`, `dropouts[]`.
3. Join item stats with content on `id`.
4. Derive everything client-side (mean/median, per-class accuracy, dropout
   categories). No data is cached between refreshes.

No auto-polling. Manual Refresh only.

## Widgets

- **Hero LED** — amber seven-segment readout that rotates 5 facts on a 5s
  cycle.
- **Score Distribution** — Observable Plot bar chart of session scores 0–10
  with dashed mean and solid median overlays. Readouts above show the exact
  mean and median.
- **REAL DETECTOR / AI DETECTOR** — two hand-rolled SVG half-circle analog
  gauges. Ticks at 0/25/50/75/100; 50% labelled "CHANCE". Needle angle =
  accuracy. Below each gauge, the exact percentage in an LED readout.
- **Started vs Finished** — three LEDs: total sessions ever started, total
  finished, and dropped (started − finished).
- **Dropout Map** — Observable Plot scatter. X = items answered at quit, Y =
  accuracy at quit. Each dot has a distinct **shape AND color** by category
  (circle / red = FRUSTRATED, square / neutral = MIXED, triangle / green =
  BORED). Shape is the 508 backup for color.

## Themes

Two palettes, toggled via the `THEME:` button in the status bar. The current
page-load theme persists until refresh; no localStorage (per project rules).

- **Vault-Tec** (default) — beige chassis, amber primary, teal secondary.
  Credible and neutral; the right default for Census.
- **Pip-Boy** — dark-green CRT chassis with subtle scanlines, phosphor
  monochrome accents. Lands well with Scouts.

Both themes are WCAG AA compliant. Contrast math is documented in the 2026-04-21
handoff.

## Files

- `index.html` — page skeleton + script imports.
- `dashboard.css` — single file, both themes via `:root[data-theme="…"]`.
- `dashboard.js` — all fetching, math, rendering, theme toggle.
- `README.md` — this file.

## External dependencies

- [Observable Plot](https://observablehq.com/plot/) — used for the score
  distribution and dropout scatter. Loaded via CDN.
- [DSEG7 Classic](https://github.com/keshikan/DSEG) — seven-segment font for
  LED numerics. Loaded via CDN. If the font fails to load, the browser falls
  back to monospace and readouts remain legible.

No build step, no npm, no bundler.

## Backend fields consumed

From `CONFIG.APPS_SCRIPT_URL` GET:

```
{
  total_sessions: number,         // back-compat = sessions_completed
  item_stats: [
    { item_id, times_shown, times_correct, accuracy }, ...
  ],
  score_distribution: [
    { score: 0..10, count: number }, ...
  ],
  sessions_started:   number,     // v2: total population ever started
  sessions_completed: number,     // v2: subset that finished
  dropouts: [                     // v2: one per abandoned session
    { session_id, items_answered, accuracy_at_quit }, ...
  ]
}
```

The frontend **tolerates missing v2 fields**: `sessions_started` falls back
to `total_sessions`, `sessions_completed` falls back to `total_sessions`, and
`dropouts` falls back to `[]`. If the backend hasn't been redeployed yet, the
dashboard shows `DROPPED = 0` and `NO DROPOUTS YET` rather than error.

## Known limitations

- **No auto-refresh.** Manual Refresh only. Apps Script has quota limits and
  the operator typically wants to control screen updates.
- **No cohort segmentation**, no time windowing, no per-session drilldown
  (all v1 scope-outs carried forward).
- **No Wilson CI, no halos, no uncertainty arcs.** The teaching moment in v2
  lives in the distribution and dials, not in fuzzy edges. The `wilson95`
  utility in `dashboard.js` is retained unreferenced for future use.
- **Dropout categories are heuristic.** Accuracy < 40% → FRUSTRATED,
  > 70% → BORED, else MIXED. These thresholds are deliberately visible in
  the code (`DROP_FRUSTRATED_T`, `DROP_BORED_T`) so they can be tuned.
- **Session IDs never appear in the UI.** The backend exposes them for
  deduplication but they are opaque internal keys.

## Local development

```
python3 -m http.server 8000   # from repo root
# Open http://localhost:8000/stats/
```

Opening `stats/index.html` directly via `file://` works but CORS handling on
a null origin is browser-dependent; prefer the local HTTP server.

## Deployment

1. Edit `backend/apps-script.gs` (only `_readAggregates` is touched in v2).
2. Deploy the Apps Script web app from the Apps Script editor (**must be
   done manually** — Claude Code cannot deploy Apps Script).
3. Commit/push the `stats/` changes; GitHub Pages picks them up automatically
   once on `main`.

Until step 2 is performed, the dashboard shows correct-but-degraded values:
`STARTED` and `FINISHED` are equal, `DROPPED = 0`, and the dropout scatter
reads `NO DROPOUTS YET`. No errors, no crashes.
