# Content Ingest Pipeline — Design Spec

**Date**: 2026-03-29
**Status**: Approved
**Related**: AD-001 (system design), AD-009 (CLI over MCP for internal tools)

## Problem

Adding content to the game is a manual JSON-editing process. We need a pipeline that:
- Processes local image/video files with automated metadata extraction
- Uses Claude Code (subscription, no API costs) for vision-based analysis
- Gives the curator explicit control over review and promotion
- Hosts all media in the repo (`assets/`) served via GitHub Pages

## Design Principles

- **Three deliberate stages**: auto-ingest, review, promote. Each requires an explicit command.
- **Python for file ops, Claude Code for vision**: no Anthropic API key needed.
- **Metadata provenance**: every auto-filled field carries a `source` tag so the curator knows what's a guess vs. a fact.
- **Idempotent and resumable**: re-running any stage is safe. Review can be interrupted and resumed.

## Directory Layout

```
ai-or-not/
├── ingest/              # Drop zone for raw files. Gitignored.
├── staged/              # Auto-processed items awaiting review. Gitignored.
│   └── img-021/
│       ├── img-021.jpg  # Optimized media file
│       ├── thumbnail.jpg # Video thumbnail (videos only)
│       └── metadata.json # Extracted + inferred metadata
├── assets/              # Production media. Committed. Served by GitHub Pages.
├── content.json         # Production metadata. Committed.
├── data/
│   └── item_stats.json  # Computed difficulty stats (from analysis scripts)
└── tools/
    ├── auto_ingest.py
    ├── review_staged.py
    ├── promote.py
    ├── requirements.txt
    ├── ingest_config.yaml
    └── lib/
        ├── __init__.py
        ├── content.py   # content.json read/write, ID generation
        ├── extract.py   # EXIF, file type detection, video thumbnails
        └── files.py     # File operations, image optimization
```

`ingest/` and `staged/` are gitignored. `assets/` and `content.json` are committed.

## Stage 1: Auto-Ingest

**Command**: `python tools/auto_ingest.py` (processes 1 file, default) or `--all`

**Input**: Raw files in `ingest/`. Supported formats: jpg, jpeg, png, webp, gif, mp4, webm, mov.

**Processing per file:**

1. **File detection** — mime type from extension + magic bytes. Classify as image or video.
2. **ID assignment** — next available `img-NNN` or `vid-NNN` based on both `content.json` and existing staged items.
3. **Image optimization** — resize to max 1200px wide (preserves aspect ratio), convert to JPEG at quality 85. Original is untouched.
4. **Video processing** — validate duration (reject >30s), file size (reject >50MB). Extract thumbnail from middle frame via ffmpeg. Copy file as-is (user pre-edits videos to target quality).
5. **EXIF extraction** (images only) — camera model, date taken, software field. Software is a strong signal: Photoshop/Lightroom = real camera workflow; Stable Diffusion/ComfyUI = AI.
6. **Write staged output** — create `staged/{id}/` with optimized media + `metadata.json`.
7. **Move source file** from `ingest/` to `staged/{id}/original.{ext}` — prevents double-processing, preserves original.

**metadata.json schema** (after auto-ingest, before vision):

```json
{
  "id": "img-021",
  "media_type": "image",
  "original_filename": "cool_landscape.png",
  "file_size_kb": 342,
  "dimensions": "1200x800",
  "is_ai": null,
  "category": null,
  "source": null,
  "attribution": null,
  "license": null,
  "explanation": null,
  "generation_method": null,
  "prior_difficulty": null,
  "tags": null,
  "exif": {
    "camera": null,
    "software": "Stable Diffusion",
    "date": null
  },
  "auto_ingest_date": "2026-03-29T10:30:00Z",
  "review_status": "pending"
}
```

Fields the tool fills: `id`, `media_type`, `original_filename`, `file_size_kb`, `dimensions`, `exif.*`, `auto_ingest_date`, `review_status`. Everything else is `null` until vision or curator fills it.

## Stage 1.5: Vision Analysis (Claude Code)

**Not a Python script.** This step is performed by Claude Code in your current session (or via ClaudeClaw).

**Workflow**: After auto-ingest, ask Claude Code to analyze staged items. Claude Code:

1. Reads each staged image file (it can view images natively)
2. For each item, infers: `is_ai` (with confidence), `category`, `tags`, `explanation` draft, `generation_method` guess
3. Writes results back to the item's `metadata.json`

**metadata.json fields after vision analysis:**

```json
{
  "is_ai": { "value": true, "confidence": "high", "source": "claude-vision" },
  "category": { "value": "landscape", "source": "claude-vision" },
  "tags": { "value": ["mountains", "sunset", "photorealistic"], "source": "claude-vision" },
  "explanation": { "value": "The mountains show unnaturally smooth gradients...", "source": "claude-vision" },
  "generation_method": { "value": "stable-diffusion", "source": "claude-vision" }
}
```

This is a documented workflow pattern, not a hard-coded skill. If the pattern becomes repetitive, it can be promoted to a Claude Code skill (`/ingest-analyze`) later.

**EXIF-boosted confidence**: If `exif.software` indicates an AI tool, Claude Code should factor that into its `is_ai` assessment. If EXIF shows a real camera, same.

## Stage 2: Curator Review

**Command**: `python tools/review_staged.py`

Shows only items with `review_status: "pending"` (default). Use `--all` to re-review everything.

**Per item:**

1. **Opens the image** in default viewer (macOS `open` command)
2. **Displays auto-filled fields** with source tags and confidence:
   ```
   ── img-021 (landscape.png) ──────────────────
   is_ai:       true  [claude-vision, high confidence]
   category:    landscape  [claude-vision]
   tags:        mountains, sunset, photorealistic  [claude-vision]
   explanation:  "The mountains show..."  [claude-vision]
   gen_method:  stable-diffusion  [claude-vision]
   exif.software: Stable Diffusion  [exif]

   NEEDS YOUR INPUT:
     source:           ___
     attribution:      ___
     license:          ___
     prior_difficulty:  ___
   ```
3. **For each auto-filled field**: press Enter to accept, or type a new value to override
4. **For null fields**, prompt with helpers:
   - `license`: numbered list of common options (CC0-1.0, CC-BY-4.0, Unsplash License, etc.)
   - `prior_difficulty`: show the 0.0-1.0 scale with guide text
   - `source` and `attribution`: free text
5. **Show complete record**, ask: `[a]pprove / [e]dit / [s]kip / [r]eject`
   - **approve** — sets `review_status: "approved"`
   - **edit** — pick a field number to change
   - **skip** — leaves as `pending`, move to next item
   - **reject** — sets `review_status: "rejected"`, optionally deletes staged directory

**Resumable**: quit anytime, run again later. Only `pending` items shown by default.

## Stage 3: Promote

**Command**: `python tools/promote.py`

**Input**: Staged items with `review_status: "approved"`.

**Per item:**

1. Copy media file from `staged/{id}/{id}.{ext}` to `assets/{id}.{ext}`
2. Flatten metadata.json into production schema — strip source tags, confidence, exif block, review_status. Just the clean field values.
3. Set `url` to `assets/{id}.{ext}` (relative path, works on GitHub Pages)
4. Append item to `content.json` items array
5. Update `content.json` meta.last_updated
6. Delete the staged directory for that item

**CLI flow:**

```
$ python tools/promote.py

Found 3 approved items:

  img-021  landscape  AI (stable-diffusion)  difficulty: 0.7
  img-022  animal     Real (photograph)       difficulty: 0.4
  vid-005  scene      AI (sora)               difficulty: 0.8

Promote all? [y/n/pick]
```

**Does not auto-commit.** Prints a reminder:
```
Promoted 3 items. content.json now has 23 items (12 AI, 11 real).
Assets: 23 files, 18.4 MB total.

Next: git add assets/ content.json && git commit && git push
```

## Difficulty Tracking

Three distinct difficulty values per item:

| Field | Set by | Stored in | When |
|-------|--------|-----------|------|
| `prior_difficulty` | Curator | `content.json` | At promote time. Set once, never changes. |
| `observed_difficulty` | Computed | `data/item_stats.json` | From play data: 1 - (correct / shown) |
| `bayesian_difficulty` | Computed | `data/item_stats.json` | Posterior mean from Beta-Binomial update |

`content.json` is static curator metadata. `data/item_stats.json` is computed by analysis scripts or exported from the backend. The game frontend can optionally fetch `item_stats.json` for richer results display.

## Migration Plan

The current `content.json` has 10 Unsplash hotlinks and 10 placeholder AI items. Migration:

1. Download the 10 Unsplash images into `assets/`, optimize to pipeline standards
2. Update their `url` fields in `content.json` to `assets/{id}.jpg`
3. Remove the 10 placeholder AI items (they have no real URLs)
4. Result: 10 real items in `assets/`, served locally, ready for the game

This can be a one-time migration script (`tools/migrate_existing.py`) or done manually. New content goes through the full pipeline.

## Dependencies

**tools/requirements.txt:**
```
Pillow
ffmpeg-python
pyyaml
```

**System dependency**: `ffmpeg` binary (for video thumbnail extraction via ffmpeg-python).

**No Anthropic SDK.** Vision analysis runs through Claude Code subscription.

**Config** (`tools/ingest_config.yaml`):
```yaml
vision_model: claude-vision  # informational only, used by Claude Code session
max_image_width: 1200
image_quality: 85
max_video_duration_sec: 30
max_video_file_mb: 50
assets_dir: assets
staged_dir: staged
ingest_dir: ingest
content_json: content.json
```

## What NOT To Do

- Do not call the Anthropic API directly — vision analysis runs through Claude Code subscription
- Do not auto-commit or auto-push — the curator commits deliberately
- Do not store computed difficulty in content.json — that goes in data/item_stats.json
- Do not delete originals — they're preserved in staged/{id}/original.{ext} until promotion
- Do not process files in-place in ingest/ — always copy/move to staged/
- Do not require internet access for stages 1, 2, or 3 — only stage 1.5 (vision) needs Claude Code
