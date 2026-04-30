/* =============================================================
   AI or Not? — Live Data Station v2 · dashboard.js

   Data flow:
     1. GET ../content.json          → item library (for is_ai ground truth)
     2. GET CONFIG.APPS_SCRIPT_URL   → aggregates payload
     3. Join item_stats with content on item_id
     4. Derive per-widget values (means/medians, dial values, dropout cats)
     5. Render: hero LED cycle, distribution, two dials, meter, scatter

   Backend extensions (v2) expected but tolerated if missing:
     - sessions_started    (falls back to total_sessions)
     - sessions_completed  (falls back to total_sessions)
     - dropouts[]          (falls back to [])

   Manual refresh only. No auto-polling. No fake data. No Wilson CI UI.
   ============================================================= */

"use strict";

// ---------- Tunables ----------
const HERO_CYCLE_MS     = 5000;
const MIN_N_FOR_HARDEST = 5;            // spec: times_shown >= 5
const DROP_LOW_T        = 0.35;         // accuracy < 0.35 → low-accuracy dropout
const DROP_HIGH_T       = 0.75;         // accuracy > 0.75 → high-accuracy dropout

// Shape mapping for the three dropout accuracy bands.
// Shape is the 508 backup to color — no color-only cues.
const DROP_SYMBOL = {
  low:  "circle",
  mid:  "square",
  high: "triangle"
};

// ---------- Mutable module state ----------
let contentIndex = null;
let lastJoined   = null;
let lastStats    = null;
let lastDerived  = null;   // cached derived values for re-render on theme change
let heroFacts    = [];
let heroIdx      = 0;
let heroTimer    = null;

// ---------- Shortcuts ----------
const $ = (id) => document.getElementById(id);

// =============================================================
// Wilson 95% interval — retained as a utility per spec.
// No widget renders this visually; callers may depend on the
// export in the future. Kept here so the deletion history is
// explicit in git for anyone grepping for the math.
// =============================================================
function wilson95(k, n) {
  if (n <= 0) return { lo: 0, hi: 1, width: 1 };
  const z = 1.96, z2 = z * z;
  const p = k / n;
  const d = 1 + z2 / n;
  const c = (p + z2 / (2 * n)) / d;
  const m = (z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / d;
  return { lo: Math.max(0, c - m), hi: Math.min(1, c + m), width: 2 * m };
}

// =============================================================
// Formatting helpers
// =============================================================
function fmtPct1(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return "--.-";
  return (x * 100).toFixed(1);
}
function fmtTime(d = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
function themeVar(name) {
  return getComputedStyle(document.body).getPropertyValue(`--${name}`).trim();
}

// =============================================================
// Fetch
// =============================================================
async function fetchContent() {
  const res = await fetch("../content.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`content.json fetch failed: HTTP ${res.status}`);
  const body = await res.json();
  if (!body || !Array.isArray(body.items)) {
    throw new Error("content.json structure invalid — expected { items: [...] }");
  }
  return body.items;
}
async function fetchAggregates() {
  if (typeof CONFIG === "undefined" || !CONFIG.APPS_SCRIPT_URL) {
    throw new Error("CONFIG.APPS_SCRIPT_URL missing — ensure ../config.js is loaded.");
  }
  const res = await fetch(CONFIG.APPS_SCRIPT_URL, { method: "GET", cache: "no-store" });
  if (!res.ok) throw new Error(`aggregates fetch failed: HTTP ${res.status}`);
  const body = await res.json();
  if (typeof body.total_sessions !== "number" || !Array.isArray(body.item_stats)) {
    throw new Error("aggregates payload missing required fields.");
  }
  return body;
}

function buildContentIndex(items) {
  const idx = new Map();
  for (const item of items) {
    if (!item.id) continue;
    idx.set(item.id, item);
  }
  return idx;
}

function joinStats(rawItemStats, contentIdx) {
  const rows = [];
  for (const row of rawItemStats) {
    const item = contentIdx.get(String(row.item_id));
    if (!item) continue; // ignore orphan rows
    const times_shown   = Number(row.times_shown) || 0;
    const times_correct = Number(row.times_correct) || 0;
    rows.push({
      id: item.id,
      is_ai: item.is_ai === true,
      times_shown,
      times_correct
    });
  }
  return rows;
}

// =============================================================
// Derived values (computed once per refresh, cached for theme toggle)
// =============================================================
function deriveAll(stats, contentIdx) {
  const joined = joinStats(stats.item_stats || [], contentIdx);

  // Overall k/n
  let K = 0, N = 0;
  for (const r of joined) { K += r.times_correct; N += r.times_shown; }

  // Per-class k/n
  let realK = 0, realN = 0, aiK = 0, aiN = 0;
  for (const r of joined) {
    if (r.is_ai) { aiK += r.times_correct; aiN += r.times_shown; }
    else         { realK += r.times_correct; realN += r.times_shown; }
  }

  // Hardest item (lowest accuracy among items with N ≥ threshold)
  const eligible = joined.filter(r => r.times_shown >= MIN_N_FOR_HARDEST);
  let hardest = null;
  if (eligible.length) {
    hardest = eligible.reduce((m, x) => {
      const ax = x.times_correct / x.times_shown;
      const am = m.times_correct / m.times_shown;
      return ax < am ? x : m;
    }, eligible[0]);
  }

  // Score distribution → mean + median
  const dist = Array.isArray(stats.score_distribution) ? stats.score_distribution : [];
  const normDist = dist.map(d => ({ score: Number(d.score), count: Number(d.count) || 0 }));
  let totalCount = 0, sumScores = 0;
  for (const d of normDist) { totalCount += d.count; sumScores += d.score * d.count; }
  const mean = totalCount > 0 ? sumScores / totalCount : null;

  // Median: first score whose cumulative count crosses totalCount/2.
  // With integer scores and multi-modal distributions we still want
  // *a* median that lands on an integer tick — we pick the first
  // score where cumulative ≥ halfway, which is the standard
  // discrete-distribution median.
  let median = null;
  if (totalCount > 0) {
    const half = totalCount / 2;
    let cum = 0;
    for (const d of normDist) {
      cum += d.count;
      if (cum >= half) { median = d.score; break; }
    }
  }

  // Started / finished / dropped (tolerate missing backend fields)
  const completed = Number.isFinite(stats.sessions_completed)
                    ? Number(stats.sessions_completed)
                    : Number(stats.total_sessions) || 0;
  const started   = Number.isFinite(stats.sessions_started)
                    ? Number(stats.sessions_started)
                    : completed;
  const dropped   = Math.max(0, started - completed);
  const dropoutRate = started > 0 ? (started - completed) / started : 0;

  // Dropout records → tagged categories
  const dropouts = Array.isArray(stats.dropouts) ? stats.dropouts : [];
  const tagged = dropouts.map(d => {
    const acc = Number(d.accuracy_at_quit) || 0;
    const n   = Number(d.items_answered) || 0;
    let category;
    if (acc < DROP_LOW_T)       category = "low";
    else if (acc > DROP_HIGH_T) category = "high";
    else                        category = "mid";
    return { items_answered: n, accuracy_at_quit: acc, category };
  });
  const counts = { low: 0, mid: 0, high: 0 };
  for (const t of tagged) counts[t.category]++;

  return {
    joined,
    overall: { k: K, n: N, acc: N > 0 ? K / N : null },
    real:    { k: realK, n: realN, acc: realN > 0 ? realK / realN : null },
    ai:      { k: aiK,   n: aiN,   acc: aiN   > 0 ? aiK   / aiN   : null },
    hardest,
    distribution: normDist,
    mean, median,
    sessions: { started, completed, dropped, rate: dropoutRate },
    dropouts: tagged,
    dropoutCounts: counts
  };
}

// =============================================================
// Widget: Hero LED cycle (v2 fact list)
// =============================================================
function computeHeroFacts(d) {
  const rate = d.sessions.started > 0 ? (d.sessions.rate * 100).toFixed(1) + "%" : "--.-%";
  return [
    { label: "TOTAL PLAYS",      value: String(d.sessions.completed) },
    { label: "SESSIONS STARTED", value: String(d.sessions.started) },
    { label: "DROPOUT RATE",     value: rate },
    {
      label: `MOST MISSED ITEM (N≥${MIN_N_FOR_HARDEST})`,
      value: d.hardest ? d.hardest.id.toUpperCase() : "N/A"
    },
    { label: "OVERALL ACCURACY", value: d.overall.acc === null ? "--.-%" : fmtPct1(d.overall.acc) + "%" }
  ];
}
function renderHero(facts) {
  heroFacts = facts;
  heroIdx   = 0;
  renderHeroDots();
  showHeroFact();
  if (heroTimer) clearInterval(heroTimer);
  heroTimer = setInterval(() => {
    heroIdx = (heroIdx + 1) % heroFacts.length;
    showHeroFact();
    renderHeroDots();
  }, HERO_CYCLE_MS);
}
function showHeroFact() {
  const f = heroFacts[heroIdx];
  if (!f) return;
  $("hero-label").textContent = f.label;
  $("hero-value").textContent = f.value;
}
function renderHeroDots() {
  const host = $("hero-dots");
  host.innerHTML = "";
  for (let i = 0; i < heroFacts.length; i++) {
    const d = document.createElement("span");
    d.className = "dot" + (i === heroIdx ? " active" : "");
    host.appendChild(d);
  }
}

// =============================================================
// Widget: Score Distribution (hand-rolled SVG bar chart)
// Same stylistic vocabulary as the dials below — no chart library.
// =============================================================
function renderDistribution(d) {
  const host = $("plot-distribution");
  host.innerHTML = "";

  if (!d.distribution.length || d.distribution.every(b => b.count === 0)) {
    $("mean-value").textContent   = "--.-";
    $("median-value").textContent = "--.-";
    const empty = document.createElement("div");
    empty.className = "plot-empty";
    empty.textContent = "NO DATA YET";
    host.appendChild(empty);
    return;
  }

  $("mean-value").textContent   = (d.mean   ?? 0).toFixed(1);
  $("median-value").textContent = d.median === null ? "--.-" : d.median.toFixed(1);

  const primary   = themeVar("accent-primary")       || "#d97706";
  const secondary = themeVar("accent-secondary-led") || "#14b8a6";
  const ink       = themeVar("bezel-ink")            || "#f5ebd0";

  // Geometry
  const W = host.clientWidth || 600;
  const H = 240;
  const M = { top: 24, right: 16, bottom: 40, left: 48 };
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;

  // X scale: integer scores 0..10 mapped to [0, plotW]
  // Each bar occupies one integer's worth of horizontal space.
  const xStep = plotW / 11;                         // 11 integer positions
  const xCenter = (score) => M.left + (score + 0.5) * xStep;
  const xBar    = (score) => M.left + score * xStep + xStep * 0.1;
  const barW    = xStep * 0.8;

  // Y scale: 0..maxCount mapped to [plotH, 0] (inverted)
  const maxCount = Math.max(1, ...d.distribution.map(b => b.count));
  // Nice round y-max: round up to nearest 5.
  const yMax = Math.ceil(maxCount / 5) * 5;
  const yPos = (count) => M.top + plotH - (count / yMax) * plotH;

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", String(W));
  svg.setAttribute("height", String(H));
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Score distribution histogram with mean and median markers");

  // --- Y gridlines + labels ---
  const yTickCount = 5;
  for (let i = 0; i <= yTickCount; i++) {
    const v = (yMax / yTickCount) * i;
    const y = yPos(v);

    const grid = document.createElementNS(svgNS, "line");
    grid.setAttribute("x1", M.left);
    grid.setAttribute("x2", M.left + plotW);
    grid.setAttribute("y1", y);
    grid.setAttribute("y2", y);
    grid.setAttribute("stroke", ink);
    grid.setAttribute("stroke-opacity", i === 0 ? "0.6" : "0.15");
    grid.setAttribute("stroke-width", "1");
    svg.appendChild(grid);

    const label = document.createElementNS(svgNS, "text");
    label.setAttribute("x", M.left - 8);
    label.setAttribute("y", y + 4);
    label.setAttribute("text-anchor", "end");
    label.setAttribute("fill", ink);
    label.setAttribute("font-family", "Courier New, Menlo, monospace");
    label.setAttribute("font-size", "11");
    label.textContent = String(Math.round(v));
    svg.appendChild(label);
  }

  // --- Y axis label ---
  const yAxisLabel = document.createElementNS(svgNS, "text");
  yAxisLabel.setAttribute("x", M.left);
  yAxisLabel.setAttribute("y", M.top - 8);
  yAxisLabel.setAttribute("text-anchor", "start");
  yAxisLabel.setAttribute("fill", ink);
  yAxisLabel.setAttribute("font-family", "Courier New, Menlo, monospace");
  yAxisLabel.setAttribute("font-size", "11");
  yAxisLabel.setAttribute("font-weight", "700");
  yAxisLabel.textContent = "↑ SESSIONS";
  svg.appendChild(yAxisLabel);

  // --- Bars ---
  for (const row of d.distribution) {
    if (row.count === 0) continue;
    const y = yPos(row.count);
    const h = M.top + plotH - y;
    const bar = document.createElementNS(svgNS, "rect");
    bar.setAttribute("x", xBar(row.score));
    bar.setAttribute("y", y);
    bar.setAttribute("width", barW);
    bar.setAttribute("height", Math.max(1, h));
    bar.setAttribute("fill", primary);
    bar.setAttribute("stroke", ink);
    bar.setAttribute("stroke-width", "0.5");
    svg.appendChild(bar);
  }

  // --- X axis ticks (scores 0..10) ---
  for (let s = 0; s <= 10; s++) {
    const x = xCenter(s);
    const tick = document.createElementNS(svgNS, "line");
    tick.setAttribute("x1", x);
    tick.setAttribute("x2", x);
    tick.setAttribute("y1", M.top + plotH);
    tick.setAttribute("y2", M.top + plotH + 4);
    tick.setAttribute("stroke", ink);
    tick.setAttribute("stroke-opacity", "0.6");
    svg.appendChild(tick);

    const label = document.createElementNS(svgNS, "text");
    label.setAttribute("x", x);
    label.setAttribute("y", M.top + plotH + 18);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("fill", ink);
    label.setAttribute("font-family", "Courier New, Menlo, monospace");
    label.setAttribute("font-size", "11");
    label.textContent = String(s);
    svg.appendChild(label);
  }

  // --- X axis label ---
  const xAxisLabel = document.createElementNS(svgNS, "text");
  xAxisLabel.setAttribute("x", M.left + plotW / 2);
  xAxisLabel.setAttribute("y", H - 6);
  xAxisLabel.setAttribute("text-anchor", "middle");
  xAxisLabel.setAttribute("fill", ink);
  xAxisLabel.setAttribute("font-family", "Courier New, Menlo, monospace");
  xAxisLabel.setAttribute("font-size", "11");
  xAxisLabel.setAttribute("font-weight", "700");
  xAxisLabel.textContent = "SCORE (OUT OF 10) →";
  svg.appendChild(xAxisLabel);

  // --- Mean line + label (dashed) ---
  if (d.mean !== null && Number.isFinite(d.mean)) {
    const xM = xCenter(d.mean);
    const meanLine = document.createElementNS(svgNS, "line");
    meanLine.setAttribute("x1", xM);
    meanLine.setAttribute("x2", xM);
    meanLine.setAttribute("y1", M.top);
    meanLine.setAttribute("y2", M.top + plotH);
    meanLine.setAttribute("stroke", primary);
    meanLine.setAttribute("stroke-width", "3");
    meanLine.setAttribute("stroke-dasharray", "6,3");
    svg.appendChild(meanLine);

    const meanLabel = document.createElementNS(svgNS, "text");
    meanLabel.setAttribute("x", xM);
    meanLabel.setAttribute("y", M.top + 12);
    meanLabel.setAttribute("text-anchor", "middle");
    meanLabel.setAttribute("fill", primary);
    meanLabel.setAttribute("font-family", "Courier New, Menlo, monospace");
    meanLabel.setAttribute("font-size", "11");
    meanLabel.setAttribute("font-weight", "700");
    meanLabel.textContent = `MEAN ${d.mean.toFixed(1)}`;
    svg.appendChild(meanLabel);
  }

  // --- Median line + label (solid) ---
  if (d.median !== null && Number.isFinite(d.median)) {
    const xMd = xCenter(d.median);
    const medLine = document.createElementNS(svgNS, "line");
    medLine.setAttribute("x1", xMd);
    medLine.setAttribute("x2", xMd);
    medLine.setAttribute("y1", M.top);
    medLine.setAttribute("y2", M.top + plotH);
    medLine.setAttribute("stroke", secondary);
    medLine.setAttribute("stroke-width", "3");
    svg.appendChild(medLine);

    const medLabel = document.createElementNS(svgNS, "text");
    medLabel.setAttribute("x", xMd);
    medLabel.setAttribute("y", M.top + 28);
    medLabel.setAttribute("text-anchor", "middle");
    medLabel.setAttribute("fill", secondary);
    medLabel.setAttribute("font-family", "Courier New, Menlo, monospace");
    medLabel.setAttribute("font-size", "11");
    medLabel.setAttribute("font-weight", "700");
    medLabel.textContent = `MEDIAN ${d.median.toFixed(1)}`;
    svg.appendChild(medLabel);
  }

  host.appendChild(svg);
}

// =============================================================
// Widget: REAL / AI dials (hand-rolled SVG half-circle)
// =============================================================
function renderDial(elId, accuracy, classLabelN, classLabelKind) {
  const host = $(elId);
  host.innerHTML = "";

  const svgNS = "http://www.w3.org/2000/svg";
  const svg   = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 220 140");
  svg.setAttribute("aria-hidden", "true");

  // Arc background (half-circle from left-bottom to right-bottom, center at (110, 115), radius 90)
  const arcR  = 90;
  const cx = 110, cy = 115;
  const arcBg = document.createElementNS(svgNS, "path");
  // M = move to start of arc (left), A = elliptical arc to end (right)
  arcBg.setAttribute("d",
    `M ${cx - arcR} ${cy} A ${arcR} ${arcR} 0 0 1 ${cx + arcR} ${cy}`);
  arcBg.setAttribute("class", "dial-arc-bg");
  arcBg.setAttribute("fill", "none");
  arcBg.setAttribute("stroke-width", "22");
  arcBg.setAttribute("stroke", "var(--dial-arc)"); /* supported on SVG stroke */
  svg.appendChild(arcBg);

  // Tick marks at 0, 25, 50, 75, 100 %
  const ticks = [0, 25, 50, 75, 100];
  const tickInnerR = arcR - 14;
  const tickOuterR = arcR + 6;
  for (const t of ticks) {
    // 0% → 180°, 100% → 0°, in our clockwise-from-left convention.
    const theta = Math.PI * (1 - t / 100);
    const x1 = cx + tickInnerR * Math.cos(theta);
    const y1 = cy - tickInnerR * Math.sin(theta);
    const x2 = cx + tickOuterR * Math.cos(theta);
    const y2 = cy - tickOuterR * Math.sin(theta);

    const tick = document.createElementNS(svgNS, "line");
    tick.setAttribute("x1", x1.toFixed(2));
    tick.setAttribute("y1", y1.toFixed(2));
    tick.setAttribute("x2", x2.toFixed(2));
    tick.setAttribute("y2", y2.toFixed(2));
    tick.setAttribute("class", (t === 0 || t === 50 || t === 100) ? "dial-tick-major" : "dial-tick");
    svg.appendChild(tick);

    const label = document.createElementNS(svgNS, "text");
    const labelR = arcR + 16;
    label.setAttribute("x", (cx + labelR * Math.cos(theta)).toFixed(2));
    label.setAttribute("y", (cy - labelR * Math.sin(theta) + 3).toFixed(2));
    label.setAttribute("class", "dial-tick-label");
    label.setAttribute("text-anchor", t < 50 ? "end" : t > 50 ? "start" : "middle");
    label.textContent = String(t);
    svg.appendChild(label);

    if (t === 50) {
      const chanceLabel = document.createElementNS(svgNS, "text");
      chanceLabel.setAttribute("x", cx.toFixed(2));
      chanceLabel.setAttribute("y", (cy - (arcR + 30)).toFixed(2));
      chanceLabel.setAttribute("class", "dial-tick-label dial-chance-label");
      chanceLabel.setAttribute("text-anchor", "middle");
      chanceLabel.textContent = "CHANCE";
      svg.appendChild(chanceLabel);
    }
  }

  // Needle — 0 if no data, else acc%
  const pct = accuracy === null ? 0 : Math.max(0, Math.min(1, accuracy)) * 100;
  const theta = Math.PI * (1 - pct / 100);
  const needleR = arcR - 6;
  const needle = document.createElementNS(svgNS, "line");
  needle.setAttribute("x1", cx.toFixed(2));
  needle.setAttribute("y1", cy.toFixed(2));
  needle.setAttribute("x2", (cx + needleR * Math.cos(theta)).toFixed(2));
  needle.setAttribute("y2", (cy - needleR * Math.sin(theta)).toFixed(2));
  needle.setAttribute("class", "dial-needle");
  svg.appendChild(needle);

  // Hub
  const hub = document.createElementNS(svgNS, "circle");
  hub.setAttribute("cx", cx.toFixed(2));
  hub.setAttribute("cy", cy.toFixed(2));
  hub.setAttribute("r", "7");
  hub.setAttribute("class", "dial-hub");
  svg.appendChild(hub);

  host.appendChild(svg);

  // LED + caption
  const valueEl   = $(elId === "dial-real" ? "dial-real-value" : "dial-ai-value");
  const captionEl = $(elId === "dial-real" ? "dial-real-caption" : "dial-ai-caption");
  if (accuracy === null) {
    valueEl.textContent = "NO DATA";
  } else {
    valueEl.textContent = fmtPct1(accuracy);
  }
  captionEl.textContent = `OF ${classLabelN} ${classLabelKind} ITEMS ANSWERED`;
}

// =============================================================
// Widget: Completion Rate dial
// Uses the same hand-rolled SVG gauge vocabulary as the REAL/AI dials
// but driven by sessions.completed / sessions.started instead of an
// item-level accuracy. 0 at left, 100 at right, 50% tick unlabelled.
// =============================================================
function renderCompletionDial(d) {
  const completionPct = d.sessions.started > 0
    ? d.sessions.completed / d.sessions.started
    : 0;

  const host = $("dial-completion");
  host.innerHTML = "";

  const svgNS = "http://www.w3.org/2000/svg";
  const svg   = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 220 140");
  svg.setAttribute("aria-hidden", "true");

  const arcR = 90, cx = 110, cy = 115;

  const arcBg = document.createElementNS(svgNS, "path");
  arcBg.setAttribute("d",
    `M ${cx - arcR} ${cy} A ${arcR} ${arcR} 0 0 1 ${cx + arcR} ${cy}`);
  arcBg.setAttribute("class", "dial-arc-bg");
  arcBg.setAttribute("fill", "none");
  arcBg.setAttribute("stroke-width", "22");
  arcBg.setAttribute("stroke", "var(--dial-arc)");
  svg.appendChild(arcBg);

  // Tick marks at 0, 25, 50, 75, 100 %
  const ticks = [0, 25, 50, 75, 100];
  const tickInnerR = arcR - 14;
  const tickOuterR = arcR + 6;
  for (const t of ticks) {
    const theta = Math.PI * (1 - t / 100);
    const x1 = cx + tickInnerR * Math.cos(theta);
    const y1 = cy - tickInnerR * Math.sin(theta);
    const x2 = cx + tickOuterR * Math.cos(theta);
    const y2 = cy - tickOuterR * Math.sin(theta);

    const tick = document.createElementNS(svgNS, "line");
    tick.setAttribute("x1", x1.toFixed(2));
    tick.setAttribute("y1", y1.toFixed(2));
    tick.setAttribute("x2", x2.toFixed(2));
    tick.setAttribute("y2", y2.toFixed(2));
    tick.setAttribute("class", (t === 0 || t === 50 || t === 100) ? "dial-tick-major" : "dial-tick");
    svg.appendChild(tick);

    const label = document.createElementNS(svgNS, "text");
    const labelR = arcR + 16;
    label.setAttribute("x", (cx + labelR * Math.cos(theta)).toFixed(2));
    label.setAttribute("y", (cy - labelR * Math.sin(theta) + 3).toFixed(2));
    label.setAttribute("class", "dial-tick-label");
    label.setAttribute("text-anchor", t < 50 ? "end" : t > 50 ? "start" : "middle");
    label.textContent = String(t);
    svg.appendChild(label);
  }

  // Needle
  const pct = Math.max(0, Math.min(1, completionPct)) * 100;
  const theta = Math.PI * (1 - pct / 100);
  const needleR = arcR - 6;
  const needle = document.createElementNS(svgNS, "line");
  needle.setAttribute("x1", cx.toFixed(2));
  needle.setAttribute("y1", cy.toFixed(2));
  needle.setAttribute("x2", (cx + needleR * Math.cos(theta)).toFixed(2));
  needle.setAttribute("y2", (cy - needleR * Math.sin(theta)).toFixed(2));
  needle.setAttribute("class", "dial-needle");
  svg.appendChild(needle);

  // Hub
  const hub = document.createElementNS(svgNS, "circle");
  hub.setAttribute("cx", cx.toFixed(2));
  hub.setAttribute("cy", cy.toFixed(2));
  hub.setAttribute("r", "7");
  hub.setAttribute("class", "dial-hub");
  svg.appendChild(hub);

  host.appendChild(svg);

  $("dial-completion-value").textContent = fmtPct1(completionPct);
  $("dial-completion-caption").textContent =
    `${d.sessions.completed} OF ${d.sessions.started} SESSIONS FINISHED`;
}

// =============================================================
// Widget: Dropout Scatter (hand-rolled SVG)
//
// Shape and color are BOTH encoded — satisfies 508 rule that state
// must not be conveyed by color alone. Circle=<35%, square=35-75%,
// triangle=>75% accuracy at quit. DROP_SYMBOL names these mappings.
// =============================================================
function renderScatter(d) {
  $("count-low").textContent  = String(d.dropoutCounts.low);
  $("count-mid").textContent  = String(d.dropoutCounts.mid);
  $("count-high").textContent = String(d.dropoutCounts.high);

  const host = $("plot-scatter");
  host.innerHTML = "";

  if (!d.dropouts.length) {
    const empty = document.createElement("div");
    empty.className = "plot-empty";
    empty.textContent = "NO DROPOUTS YET";
    host.appendChild(empty);
    return;
  }

  const attention = themeVar("accent-attention-led") || "#ef4444";
  const positive  = themeVar("accent-positive-led")  || "#16a34a";
  const bezelInk  = themeVar("bezel-ink")            || "#f5ebd0";

  const W = host.clientWidth || 500;
  const H = 240;
  const M = { top: 18, right: 16, bottom: 40, left: 52 };
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;

  // X: items_answered 1..9 → center of each column
  const xStep = plotW / 9;
  const xPos = (n) => M.left + (n - 1 + 0.5) * xStep;
  // Y: accuracy 0..1 inverted
  const yPos = (acc) => M.top + plotH - acc * plotH;

  const colorFor = (cat) =>
    cat === "low"  ? attention
    : cat === "high" ? positive
    : bezelInk;

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", String(W));
  svg.setAttribute("height", String(H));
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Dropout scatter: items answered versus accuracy at quit, colored and shaped by category");

  // --- Y gridlines + labels (0%, 25%, 50%, 75%, 100%) ---
  const yTicks = [0, 0.25, 0.5, 0.75, 1.0];
  for (const v of yTicks) {
    const y = yPos(v);
    const grid = document.createElementNS(svgNS, "line");
    grid.setAttribute("x1", M.left);
    grid.setAttribute("x2", M.left + plotW);
    grid.setAttribute("y1", y);
    grid.setAttribute("y2", y);
    grid.setAttribute("stroke", bezelInk);
    grid.setAttribute("stroke-opacity", v === 0 ? "0.6" : "0.15");
    grid.setAttribute("stroke-width", "1");
    svg.appendChild(grid);

    const label = document.createElementNS(svgNS, "text");
    label.setAttribute("x", M.left - 8);
    label.setAttribute("y", y + 4);
    label.setAttribute("text-anchor", "end");
    label.setAttribute("fill", bezelInk);
    label.setAttribute("font-family", "Courier New, Menlo, monospace");
    label.setAttribute("font-size", "11");
    label.textContent = `${Math.round(v * 100)}%`;
    svg.appendChild(label);
  }

  // --- Y axis label ---
  const yAxisLabel = document.createElementNS(svgNS, "text");
  yAxisLabel.setAttribute("x", M.left);
  yAxisLabel.setAttribute("y", M.top - 4);
  yAxisLabel.setAttribute("text-anchor", "start");
  yAxisLabel.setAttribute("fill", bezelInk);
  yAxisLabel.setAttribute("font-family", "Courier New, Menlo, monospace");
  yAxisLabel.setAttribute("font-size", "11");
  yAxisLabel.setAttribute("font-weight", "700");
  yAxisLabel.textContent = "↑ ACCURACY AT QUIT";
  svg.appendChild(yAxisLabel);

  // --- Threshold lines (low/high accuracy boundaries) ---
  const lowLine = document.createElementNS(svgNS, "line");
  lowLine.setAttribute("x1", M.left);
  lowLine.setAttribute("x2", M.left + plotW);
  lowLine.setAttribute("y1", yPos(DROP_LOW_T));
  lowLine.setAttribute("y2", yPos(DROP_LOW_T));
  lowLine.setAttribute("stroke", attention);
  lowLine.setAttribute("stroke-opacity", "0.35");
  lowLine.setAttribute("stroke-dasharray", "3,3");
  lowLine.setAttribute("stroke-width", "1");
  svg.appendChild(lowLine);

  const highLine = document.createElementNS(svgNS, "line");
  highLine.setAttribute("x1", M.left);
  highLine.setAttribute("x2", M.left + plotW);
  highLine.setAttribute("y1", yPos(DROP_HIGH_T));
  highLine.setAttribute("y2", yPos(DROP_HIGH_T));
  highLine.setAttribute("stroke", positive);
  highLine.setAttribute("stroke-opacity", "0.35");
  highLine.setAttribute("stroke-dasharray", "3,3");
  highLine.setAttribute("stroke-width", "1");
  svg.appendChild(highLine);

  // --- X axis ticks (1..9) ---
  for (let n = 1; n <= 9; n++) {
    const x = xPos(n);
    const tick = document.createElementNS(svgNS, "line");
    tick.setAttribute("x1", x);
    tick.setAttribute("x2", x);
    tick.setAttribute("y1", M.top + plotH);
    tick.setAttribute("y2", M.top + plotH + 4);
    tick.setAttribute("stroke", bezelInk);
    tick.setAttribute("stroke-opacity", "0.6");
    svg.appendChild(tick);

    const label = document.createElementNS(svgNS, "text");
    label.setAttribute("x", x);
    label.setAttribute("y", M.top + plotH + 18);
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("fill", bezelInk);
    label.setAttribute("font-family", "Courier New, Menlo, monospace");
    label.setAttribute("font-size", "11");
    label.textContent = String(n);
    svg.appendChild(label);
  }

  // --- X axis label ---
  const xAxisLabel = document.createElementNS(svgNS, "text");
  xAxisLabel.setAttribute("x", M.left + plotW / 2);
  xAxisLabel.setAttribute("y", H - 6);
  xAxisLabel.setAttribute("text-anchor", "middle");
  xAxisLabel.setAttribute("fill", bezelInk);
  xAxisLabel.setAttribute("font-family", "Courier New, Menlo, monospace");
  xAxisLabel.setAttribute("font-size", "11");
  xAxisLabel.setAttribute("font-weight", "700");
  xAxisLabel.textContent = "ITEMS ANSWERED BEFORE QUITTING →";
  svg.appendChild(xAxisLabel);

  // --- Dots: shape varies by category, color varies by category ---
  // Slight horizontal jitter so overlapping points are visible.
  for (const dp of d.dropouts) {
    const cx = xPos(dp.items_answered) + (Math.random() - 0.5) * xStep * 0.4;
    const cy = yPos(dp.accuracy_at_quit);
    const color = colorFor(dp.category);
    let shape;
    if (dp.category === "low") {
      // Circle
      shape = document.createElementNS(svgNS, "circle");
      shape.setAttribute("cx", cx);
      shape.setAttribute("cy", cy);
      shape.setAttribute("r", "6");
    } else if (dp.category === "high") {
      // Triangle (equilateral, point up)
      const r = 7;
      const p1 = `${cx},${cy - r}`;
      const p2 = `${cx - r * 0.866},${cy + r * 0.5}`;
      const p3 = `${cx + r * 0.866},${cy + r * 0.5}`;
      shape = document.createElementNS(svgNS, "polygon");
      shape.setAttribute("points", `${p1} ${p2} ${p3}`);
    } else {
      // Square (mid band)
      const s = 11;
      shape = document.createElementNS(svgNS, "rect");
      shape.setAttribute("x", cx - s / 2);
      shape.setAttribute("y", cy - s / 2);
      shape.setAttribute("width", s);
      shape.setAttribute("height", s);
    }
    shape.setAttribute("fill", color);
    shape.setAttribute("stroke", color);
    shape.setAttribute("stroke-width", "1");
    shape.setAttribute("fill-opacity", "0.85");
    svg.appendChild(shape);
  }

  host.appendChild(svg);
}

// =============================================================
// Render orchestrator — re-usable for both refresh and theme-toggle
// =============================================================
function renderAll(d) {
  renderHero(computeHeroFacts(d));
  renderDistribution(d);
  renderDial("dial-real", d.real.acc, d.real.n, "REAL");
  renderDial("dial-ai",   d.ai.acc,   d.ai.n,   "AI");
  renderCompletionDial(d);
  renderScatter(d);
}

// =============================================================
// Theme toggle
// =============================================================
function currentTheme() {
  return document.documentElement.getAttribute("data-theme") || "vaulttec";
}
function themeLabel(name) {
  return name === "pipboy" ? "THEME: PIP-BOY" : "THEME: VAULT-TEC";
}
function toggleTheme() {
  const next = currentTheme() === "pipboy" ? "vaulttec" : "pipboy";
  // CSS custom properties are defined on :root (the <html> element), so the
  // data-theme attribute must live there too — setting it on <body> leaves
  // the var definitions unchanged.
  document.documentElement.setAttribute("data-theme", next);
  $("theme-btn").textContent = themeLabel(next);
  // SVG charts read themeVar() at render time; re-render so the new palette
  // reaches marks whose colors were baked in as attributes.
  if (lastDerived) renderAll(lastDerived);
}

// =============================================================
// Status bar
// =============================================================
function setState(kind, msg) {
  const led = $("state-led");
  led.classList.remove("state-led-idle", "state-led-loading", "state-led-ok", "state-led-error");
  led.classList.add(`state-led-${kind}`);
  $("status-message").textContent = msg;
}
function setSessionsLabel(n) { $("status-sessions").textContent = `N=${n ?? 0}`; }
function setRefreshTimestamp(d) { $("status-timestamp").textContent = fmtTime(d); }

// =============================================================
// Refresh cycle
// =============================================================
async function refresh() {
  const btn = $("refresh-btn");
  btn.disabled = true;
  $("rack").classList.add("loading");
  setState("loading", "UPDATING…");

  try {
    const [items, stats] = await Promise.all([fetchContent(), fetchAggregates()]);
    contentIndex = buildContentIndex(items);
    lastStats    = stats;
    lastDerived  = deriveAll(stats, contentIndex);

    renderAll(lastDerived);

    // Prefer sessions_completed so the status bar tracks the same number
    // the hero LED reports as TOTAL PLAYS. total_sessions still exists for
    // back-compat but can drift if ScoreDistribution and Sessions diverge.
    setSessionsLabel(stats.sessions_completed ?? stats.total_sessions);
    setRefreshTimestamp(new Date());
    setState("ok", "NOMINAL");
  } catch (err) {
    console.error("[stats] refresh failed:", err);
    setState("error", "BACKEND UNREACHABLE — RETRY");
  } finally {
    btn.disabled = false;
    $("rack").classList.remove("loading");
  }
}

// =============================================================
// Wire up
// =============================================================
function init() {
  $("refresh-btn").addEventListener("click", refresh);
  $("theme-btn").addEventListener("click", toggleTheme);
  $("theme-btn").textContent = themeLabel(currentTheme());
  // Re-render charts on resize — Plot bakes width at render time.
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (lastDerived) renderAll(lastDerived); }, 120);
  });
  refresh();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
