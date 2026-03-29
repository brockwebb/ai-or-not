# Content Ingest Pipeline

CLI tools for adding content to the AI or Not? game.

## Setup

```bash
pip install -r tools/requirements.txt
```

Requires `ffmpeg` for video support: `brew install ffmpeg`

## Workflow

### 1. Drop files in `ingest/`

Put images (jpg, png, webp) or videos (mp4, webm, mov) in the `ingest/` directory.

### 2. Auto-ingest

```bash
python tools/auto_ingest.py          # Process 1 file (default)
python tools/auto_ingest.py --all    # Process all files
python tools/auto_ingest.py --count 5  # Process 5 files
```

Extracts EXIF data, optimizes images (max 1200px, JPEG q85), creates video thumbnails, and stages items in `staged/`.

### 3. Vision analysis (Claude Code)

Ask Claude Code to analyze the staged items. It reads each image and fills in metadata fields:
- `is_ai` — AI-generated or real?
- `category` — person/animal/landscape/object/scene
- `tags` — descriptive tags
- `explanation` — educational text about visual clues
- `generation_method` — which AI model, or "photograph"

Example prompt: "Analyze the staged items in `staged/` — read each image, infer the metadata fields, and write them to the metadata.json files."

### 4. Review

```bash
python tools/review_staged.py        # Review pending items
python tools/review_staged.py --all  # Re-review all items
```

Interactive CLI walkthrough. For each item:
- Opens the image in your viewer
- Shows auto-filled fields with source tags
- Prompts for missing fields (source, attribution, license, difficulty)
- Approve, skip, or reject

Resumable — quit anytime, pending items persist.

### 5. Promote

```bash
python tools/promote.py
```

Moves approved items to `assets/` and appends to `content.json`. Prints a summary. Does **not** auto-commit.

### 6. Commit and push

```bash
git add assets/ content.json
git commit -m "feat: add new content items"
git push
```

## Configuration

Edit `tools/ingest_config.yaml` to adjust:
- `max_image_width` — resize threshold (default: 1200px)
- `image_quality` — JPEG quality (default: 85)
- `max_video_duration_sec` — reject videos over this length (default: 30s)
- `max_video_file_mb` — reject videos over this size (default: 50MB)

## Directory Layout

| Directory | Committed? | Purpose |
|-----------|-----------|---------|
| `ingest/` | No (gitignored) | Drop zone for raw files |
| `staged/` | No (gitignored) | Processed items awaiting review |
| `assets/` | Yes | Production media served by GitHub Pages |

## Running Tests

```bash
python -m pytest tests/tools/ -v
```
