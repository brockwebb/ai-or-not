# Ingest Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-stage content ingest pipeline (auto-ingest → review → promote) that processes local image/video files into the game's content library.

**Architecture:** Python CLI scripts in `tools/` with shared library in `tools/lib/`. Files flow from `ingest/` → `staged/` → `assets/` + `content.json`. Vision analysis is performed by Claude Code (not the scripts). No Anthropic API key needed.

**Tech Stack:** Python 3, Pillow (image processing), ffmpeg-python (video), PyYAML (config), argparse (CLI).

**Spec:** `docs/superpowers/specs/2026-03-29-ingest-pipeline-design.md`

---

## File Map

| File | Responsibility |
|------|---------------|
| `tools/lib/__init__.py` | Package marker |
| `tools/lib/content.py` | Read/write content.json, generate next item ID |
| `tools/lib/extract.py` | EXIF extraction, file type detection, video probing |
| `tools/lib/files.py` | Image optimization, file copy/move, directory creation |
| `tools/auto_ingest.py` | Stage 1 CLI: process files from ingest/ into staged/ |
| `tools/review_staged.py` | Stage 2 CLI: interactive review of staged items |
| `tools/promote.py` | Stage 3 CLI: move approved items to assets/ + content.json |
| `tools/migrate_existing.py` | One-time: download Unsplash images, update content.json |
| `tools/ingest_config.yaml` | Pipeline configuration |
| `tools/requirements.txt` | Python dependencies |
| `tests/tools/test_content.py` | Tests for tools/lib/content.py |
| `tests/tools/test_extract.py` | Tests for tools/lib/extract.py |
| `tests/tools/test_files.py` | Tests for tools/lib/files.py |
| `tests/tools/conftest.py` | Shared fixtures (temp dirs, sample images, sample content.json) |

---

### Task 1: Project scaffolding and config

**Files:**
- Create: `tools/__init__.py`, `tools/lib/__init__.py`
- Create: `tools/requirements.txt`
- Create: `tools/ingest_config.yaml`
- Modify: `.gitignore`

- [ ] **Step 1: Create tools directory structure**

```bash
mkdir -p tools/lib tests/tools
```

- [ ] **Step 2: Create `tools/__init__.py` and `tools/lib/__init__.py`**

Both are empty files:
```python
# tools/__init__.py
```
```python
# tools/lib/__init__.py
```

- [ ] **Step 3: Create `tools/requirements.txt`**

```
Pillow
ffmpeg-python
pyyaml
```

- [ ] **Step 4: Create `tools/ingest_config.yaml`**

```yaml
max_image_width: 1200
image_quality: 85
max_video_duration_sec: 30
max_video_file_mb: 50
assets_dir: assets
staged_dir: staged
ingest_dir: ingest
content_json: content.json
supported_image_ext: [".jpg", ".jpeg", ".png", ".webp", ".gif"]
supported_video_ext: [".mp4", ".webm", ".mov"]
```

- [ ] **Step 5: Update `.gitignore`**

Add these lines to the existing `.gitignore`:
```
ingest/
staged/
```

- [ ] **Step 6: Create `tests/tools/conftest.py`** with shared fixtures

```python
import json
import os
import shutil
import tempfile

import pytest
from PIL import Image


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project directory structure for testing."""
    dirs = ["ingest", "staged", "assets", "data"]
    for d in dirs:
        (tmp_path / d).mkdir()

    content = {
        "version": "1.0.0",
        "meta": {
            "description": "Test content",
            "license": "MIT",
            "curator": "test",
            "last_updated": "2026-01-01",
        },
        "items": [
            {
                "id": "img-001",
                "media_type": "image",
                "url": "assets/img-001.jpg",
                "is_ai": False,
                "source": "Test",
                "attribution": "Test attribution",
                "license": "CC0-1.0",
                "explanation": "Test explanation",
                "category": "landscape",
                "generation_method": "photograph",
                "prior_difficulty": 0.5,
                "tags": ["test"],
            }
        ],
    }
    (tmp_path / "content.json").write_text(json.dumps(content, indent=2))
    return tmp_path


@pytest.fixture
def sample_image(tmp_path):
    """Create a sample JPEG image for testing."""
    img = Image.new("RGB", (2400, 1600), color=(100, 150, 200))
    path = tmp_path / "test_photo.jpg"
    img.save(str(path), "JPEG")
    return path


@pytest.fixture
def sample_png(tmp_path):
    """Create a sample PNG image for testing."""
    img = Image.new("RGBA", (800, 600), color=(50, 100, 150, 255))
    path = tmp_path / "ai_art.png"
    img.save(str(path), "PNG")
    return path


@pytest.fixture
def sample_video(tmp_path):
    """Create a minimal MP4 file for testing. Requires ffmpeg."""
    path = tmp_path / "clip.mp4"
    # Generate a 3-second test video with ffmpeg
    os.system(
        f'ffmpeg -y -f lavfi -i color=c=blue:s=640x480:d=3 '
        f'-c:v libx264 -pix_fmt yuv420p -loglevel error "{path}"'
    )
    if not path.exists():
        pytest.skip("ffmpeg not available for video test")
    return path
```

- [ ] **Step 7: Install dependencies and verify**

```bash
pip install -r tools/requirements.txt
pytest tests/tools/conftest.py --co -q  # collect-only to verify fixtures parse
```

- [ ] **Step 8: Commit**

```bash
git add tools/ tests/tools/ .gitignore
git commit -m "feat: scaffold ingest pipeline directories and config"
```

---

### Task 2: Shared library — `tools/lib/content.py`

**Files:**
- Create: `tools/lib/content.py`
- Create: `tests/tools/test_content.py`

- [ ] **Step 1: Write tests for content.json operations**

Create `tests/tools/test_content.py`:

```python
import json
import pytest
from tools.lib.content import load_content, save_content, next_item_id


class TestLoadContent:
    def test_loads_valid_content(self, tmp_project):
        content = load_content(tmp_project / "content.json")
        assert content["version"] == "1.0.0"
        assert len(content["items"]) == 1
        assert content["items"][0]["id"] == "img-001"

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_content(tmp_path / "nope.json")

    def test_raises_on_invalid_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json {{{")
        with pytest.raises(json.JSONDecodeError):
            load_content(bad)


class TestSaveContent:
    def test_roundtrip(self, tmp_project):
        content = load_content(tmp_project / "content.json")
        content["items"].append({"id": "img-002", "media_type": "image"})
        save_content(tmp_project / "content.json", content)
        reloaded = load_content(tmp_project / "content.json")
        assert len(reloaded["items"]) == 2

    def test_updates_last_updated(self, tmp_project):
        content = load_content(tmp_project / "content.json")
        save_content(tmp_project / "content.json", content)
        reloaded = load_content(tmp_project / "content.json")
        assert reloaded["meta"]["last_updated"] != "2026-01-01"


class TestNextItemId:
    def test_next_image_id_from_content(self, tmp_project):
        content = load_content(tmp_project / "content.json")
        assert next_item_id(content, "image", staged_dir=None) == "img-002"

    def test_next_video_id_no_existing(self, tmp_project):
        content = load_content(tmp_project / "content.json")
        assert next_item_id(content, "video", staged_dir=None) == "vid-001"

    def test_accounts_for_staged_items(self, tmp_project):
        content = load_content(tmp_project / "content.json")
        staged = tmp_project / "staged"
        (staged / "img-002").mkdir()
        (staged / "img-003").mkdir()
        assert next_item_id(content, "image", staged_dir=staged) == "img-004"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_content.py -v
```

Expected: ImportError — `tools.lib.content` doesn't exist yet.

- [ ] **Step 3: Implement `tools/lib/content.py`**

```python
"""Read/write content.json and generate sequential item IDs."""

import json
import re
from datetime import date, timezone
from pathlib import Path


def load_content(path: Path) -> dict:
    """Load and parse content.json. Raises FileNotFoundError or JSONDecodeError."""
    with open(path) as f:
        return json.load(f)


def save_content(path: Path, content: dict) -> None:
    """Write content.json with updated last_updated timestamp."""
    content["meta"]["last_updated"] = date.today().isoformat()
    with open(path, "w") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
        f.write("\n")


def next_item_id(content: dict, media_type: str, staged_dir: Path | None) -> str:
    """Return the next available ID like 'img-004' or 'vid-002'.

    Checks both content.json items and staged/ directories to avoid collisions.
    """
    prefix = "img" if media_type == "image" else "vid"
    pattern = re.compile(rf"^{prefix}-(\d+)$")

    max_num = 0

    # Check content.json
    for item in content.get("items", []):
        m = pattern.match(item["id"])
        if m:
            max_num = max(max_num, int(m.group(1)))

    # Check staged directories
    if staged_dir and staged_dir.is_dir():
        for entry in staged_dir.iterdir():
            if entry.is_dir():
                m = pattern.match(entry.name)
                if m:
                    max_num = max(max_num, int(m.group(1)))

    return f"{prefix}-{max_num + 1:03d}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tools/test_content.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/content.py tests/tools/test_content.py
git commit -m "feat: add content.json read/write and ID generation"
```

---

### Task 3: Shared library — `tools/lib/extract.py`

**Files:**
- Create: `tools/lib/extract.py`
- Create: `tests/tools/test_extract.py`

- [ ] **Step 1: Write tests for file detection and EXIF**

Create `tests/tools/test_extract.py`:

```python
import json
import pytest
from pathlib import Path
from tools.lib.extract import detect_media_type, extract_exif, probe_video


class TestDetectMediaType:
    def test_jpg(self, sample_image):
        assert detect_media_type(sample_image) == "image"

    def test_png(self, sample_png):
        assert detect_media_type(sample_png) == "image"

    def test_mp4(self, sample_video):
        assert detect_media_type(sample_video) == "video"

    def test_unsupported_raises(self, tmp_path):
        txt = tmp_path / "notes.txt"
        txt.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported"):
            detect_media_type(txt)


class TestExtractExif:
    def test_returns_dict_for_jpeg(self, sample_image):
        exif = extract_exif(sample_image)
        assert isinstance(exif, dict)
        assert "camera" in exif
        assert "software" in exif
        assert "date" in exif

    def test_returns_empty_for_non_image(self, sample_video):
        exif = extract_exif(sample_video)
        assert exif["camera"] is None
        assert exif["software"] is None
        assert exif["date"] is None


class TestProbeVideo:
    def test_returns_duration_and_dimensions(self, sample_video):
        info = probe_video(sample_video)
        assert info["duration_sec"] == pytest.approx(3.0, abs=0.5)
        assert info["width"] == 640
        assert info["height"] == 480
        assert info["file_size_mb"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_extract.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `tools/lib/extract.py`**

```python
"""File type detection, EXIF extraction, and video probing."""

import mimetypes
import subprocess
import json
from pathlib import Path

from PIL import Image
from PIL.ExifTags import TAGS

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SUPPORTED_VIDEO_EXT = {".mp4", ".webm", ".mov"}


def detect_media_type(path: Path) -> str:
    """Return 'image' or 'video' based on file extension. Raises ValueError if unsupported."""
    ext = path.suffix.lower()
    if ext in SUPPORTED_IMAGE_EXT:
        return "image"
    if ext in SUPPORTED_VIDEO_EXT:
        return "video"
    raise ValueError(f"Unsupported file type: {ext} ({path.name})")


def extract_exif(path: Path) -> dict:
    """Extract EXIF metadata from an image. Returns dict with camera, software, date."""
    result = {"camera": None, "software": None, "date": None}
    try:
        with Image.open(path) as img:
            exif_data = img._getexif()
            if not exif_data:
                return result
            decoded = {TAGS.get(k, k): v for k, v in exif_data.items()}
            result["camera"] = decoded.get("Model")
            result["software"] = decoded.get("Software")
            date_val = decoded.get("DateTimeOriginal") or decoded.get("DateTime")
            if date_val:
                result["date"] = str(date_val)
    except Exception:
        pass
    return result


def probe_video(path: Path) -> dict:
    """Probe a video file for duration, dimensions, and file size using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path.name}: {proc.stderr}")

    info = json.loads(proc.stdout)

    # Find the video stream
    video_stream = None
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise RuntimeError(f"No video stream found in {path.name}")

    duration = float(info.get("format", {}).get("duration", 0))
    file_size_mb = path.stat().st_size / (1024 * 1024)

    return {
        "duration_sec": duration,
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "file_size_mb": round(file_size_mb, 2),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tools/test_extract.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/extract.py tests/tools/test_extract.py
git commit -m "feat: add file detection, EXIF extraction, and video probing"
```

---

### Task 4: Shared library — `tools/lib/files.py`

**Files:**
- Create: `tools/lib/files.py`
- Create: `tests/tools/test_files.py`

- [ ] **Step 1: Write tests for image optimization and video thumbnails**

Create `tests/tools/test_files.py`:

```python
import pytest
from PIL import Image
from tools.lib.files import optimize_image, extract_video_thumbnail, get_image_dimensions


class TestOptimizeImage:
    def test_resizes_wide_image(self, sample_image, tmp_path):
        out = tmp_path / "optimized.jpg"
        optimize_image(sample_image, out, max_width=1200, quality=85)
        with Image.open(out) as img:
            assert img.width == 1200
            assert img.height == 800  # Maintains 3:2 ratio from 2400x1600

    def test_does_not_upscale_small_image(self, sample_png, tmp_path):
        out = tmp_path / "optimized.jpg"
        optimize_image(sample_png, out, max_width=1200, quality=85)
        with Image.open(out) as img:
            assert img.width == 800  # Original was 800, no upscale

    def test_converts_png_to_jpeg(self, sample_png, tmp_path):
        out = tmp_path / "optimized.jpg"
        optimize_image(sample_png, out, max_width=1200, quality=85)
        with Image.open(out) as img:
            assert img.format == "JPEG"
            assert img.mode == "RGB"  # RGBA converted to RGB


class TestExtractVideoThumbnail:
    def test_creates_thumbnail(self, sample_video, tmp_path):
        out = tmp_path / "thumb.jpg"
        extract_video_thumbnail(sample_video, out)
        assert out.exists()
        with Image.open(out) as img:
            assert img.width > 0
            assert img.height > 0


class TestGetImageDimensions:
    def test_returns_dimensions(self, sample_image):
        w, h = get_image_dimensions(sample_image)
        assert w == 2400
        assert h == 1600
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_files.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `tools/lib/files.py`**

```python
"""Image optimization, video thumbnails, and file dimension utilities."""

import subprocess
from pathlib import Path

from PIL import Image


def optimize_image(src: Path, dst: Path, max_width: int = 1200, quality: int = 85) -> None:
    """Resize image to max_width (preserving aspect ratio), convert to JPEG."""
    with Image.open(src) as img:
        # Convert RGBA/P to RGB for JPEG output
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

        img.save(str(dst), "JPEG", quality=quality, optimize=True)


def extract_video_thumbnail(video_path: Path, out_path: Path) -> None:
    """Extract a frame from the middle of the video as a JPEG thumbnail."""
    # Get duration first
    duration_cmd = [
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
    ]
    proc = subprocess.run(duration_cmd, capture_output=True, text=True)
    duration = float(proc.stdout.strip()) if proc.returncode == 0 else 1.0
    midpoint = duration / 2

    # Extract frame at midpoint
    cmd = [
        "ffmpeg", "-y", "-ss", str(midpoint), "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2", "-loglevel", "error", str(out_path)
    ]
    subprocess.run(cmd, check=True)


def get_image_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) of an image file."""
    with Image.open(path) as img:
        return img.width, img.height
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tools/test_files.py -v
```

Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/lib/files.py tests/tools/test_files.py
git commit -m "feat: add image optimization and video thumbnail extraction"
```

---

### Task 5: Auto-ingest CLI — `tools/auto_ingest.py`

**Files:**
- Create: `tools/auto_ingest.py`

- [ ] **Step 1: Write integration test**

Add to `tests/tools/test_auto_ingest.py`:

```python
import json
import pytest
from pathlib import Path
from tools.auto_ingest import process_file, find_ingestable_files


class TestFindIngestableFiles:
    def test_finds_images(self, tmp_project, sample_image):
        import shutil
        shutil.copy(sample_image, tmp_project / "ingest" / "photo.jpg")
        files = find_ingestable_files(tmp_project / "ingest")
        assert len(files) == 1
        assert files[0].name == "photo.jpg"

    def test_ignores_unsupported(self, tmp_project):
        (tmp_project / "ingest" / "notes.txt").write_text("hello")
        files = find_ingestable_files(tmp_project / "ingest")
        assert len(files) == 0

    def test_empty_dir(self, tmp_project):
        files = find_ingestable_files(tmp_project / "ingest")
        assert len(files) == 0


class TestProcessFile:
    def test_processes_image(self, tmp_project, sample_image):
        import shutil
        src = tmp_project / "ingest" / "photo.jpg"
        shutil.copy(sample_image, src)

        result = process_file(
            src,
            content_json=tmp_project / "content.json",
            staged_dir=tmp_project / "staged",
            max_width=1200,
            quality=85,
        )

        assert result["id"] == "img-002"
        staged_dir = tmp_project / "staged" / "img-002"
        assert staged_dir.exists()
        assert (staged_dir / "img-002.jpg").exists()
        assert (staged_dir / "original.jpg").exists()

        meta = json.loads((staged_dir / "metadata.json").read_text())
        assert meta["id"] == "img-002"
        assert meta["media_type"] == "image"
        assert meta["original_filename"] == "photo.jpg"
        assert meta["review_status"] == "pending"
        assert meta["is_ai"] is None

        # Source file should be moved out of ingest/
        assert not src.exists()

    def test_processes_video(self, tmp_project, sample_video):
        import shutil
        src = tmp_project / "ingest" / "clip.mp4"
        shutil.copy(sample_video, src)

        result = process_file(
            src,
            content_json=tmp_project / "content.json",
            staged_dir=tmp_project / "staged",
            max_width=1200,
            quality=85,
        )

        assert result["id"] == "vid-001"
        staged_dir = tmp_project / "staged" / "vid-001"
        assert (staged_dir / "vid-001.mp4").exists()
        assert (staged_dir / "thumbnail.jpg").exists()
        assert (staged_dir / "original.mp4").exists()

        meta = json.loads((staged_dir / "metadata.json").read_text())
        assert meta["media_type"] == "video"
        assert "duration_sec" in meta
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_auto_ingest.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `tools/auto_ingest.py`**

```python
#!/usr/bin/env python3
"""Stage 1: Auto-ingest files from ingest/ into staged/ with metadata extraction."""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from project root: python tools/auto_ingest.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.content import load_content, next_item_id
from tools.lib.extract import detect_media_type, extract_exif, probe_video, SUPPORTED_IMAGE_EXT, SUPPORTED_VIDEO_EXT
from tools.lib.files import optimize_image, extract_video_thumbnail, get_image_dimensions

SUPPORTED_EXT = SUPPORTED_IMAGE_EXT | SUPPORTED_VIDEO_EXT


def load_config(config_path: Path) -> dict:
    """Load ingest config YAML. Falls back to defaults if missing."""
    defaults = {
        "max_image_width": 1200,
        "image_quality": 85,
        "max_video_duration_sec": 30,
        "max_video_file_mb": 50,
        "assets_dir": "assets",
        "staged_dir": "staged",
        "ingest_dir": "ingest",
        "content_json": "content.json",
    }
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            loaded = yaml.safe_load(f) or {}
        defaults.update(loaded)
    return defaults


def find_ingestable_files(ingest_dir: Path) -> list[Path]:
    """Return list of supported media files in ingest/, sorted by name."""
    files = []
    for f in sorted(ingest_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXT:
            files.append(f)
    return files


def process_file(
    src: Path,
    content_json: Path,
    staged_dir: Path,
    max_width: int = 1200,
    quality: int = 85,
    max_video_duration: int = 30,
    max_video_size_mb: int = 50,
) -> dict:
    """Process a single file into staged/. Returns the metadata dict."""
    media_type = detect_media_type(src)
    content = load_content(content_json)
    item_id = next_item_id(content, media_type, staged_dir)

    # Create staged directory
    item_dir = staged_dir / item_id
    item_dir.mkdir(parents=True, exist_ok=True)

    ext = src.suffix.lower()
    if ext in (".png", ".webp", ".gif"):
        out_ext = ".jpg"
    else:
        out_ext = ext

    media_dest = item_dir / f"{item_id}{out_ext}"
    original_dest = item_dir / f"original{ext}"

    metadata = {
        "id": item_id,
        "media_type": media_type,
        "original_filename": src.name,
        "file_size_kb": None,
        "dimensions": None,
        "is_ai": None,
        "category": None,
        "source": None,
        "attribution": None,
        "license": None,
        "explanation": None,
        "generation_method": None,
        "prior_difficulty": None,
        "tags": None,
        "exif": {"camera": None, "software": None, "date": None},
        "auto_ingest_date": datetime.now(timezone.utc).isoformat(),
        "review_status": "pending",
    }

    if media_type == "image":
        optimize_image(src, media_dest, max_width=max_width, quality=quality)
        w, h = get_image_dimensions(media_dest)
        metadata["dimensions"] = f"{w}x{h}"
        metadata["file_size_kb"] = round(media_dest.stat().st_size / 1024, 1)
        metadata["exif"] = extract_exif(src)  # Extract from original, not optimized
    else:
        # Video
        video_info = probe_video(src)
        if video_info["duration_sec"] > max_video_duration:
            raise ValueError(
                f"Video too long: {video_info['duration_sec']:.1f}s "
                f"(max {max_video_duration}s). Trim before ingesting."
            )
        if video_info["file_size_mb"] > max_video_size_mb:
            raise ValueError(
                f"Video too large: {video_info['file_size_mb']:.1f}MB "
                f"(max {max_video_size_mb}MB). Compress before ingesting."
            )
        shutil.copy2(src, media_dest)
        metadata["dimensions"] = f"{video_info['width']}x{video_info['height']}"
        metadata["duration_sec"] = round(video_info["duration_sec"], 1)
        metadata["file_size_kb"] = round(media_dest.stat().st_size / 1024, 1)
        # Extract thumbnail
        extract_video_thumbnail(src, item_dir / "thumbnail.jpg")

    # Move original to staged dir
    shutil.move(str(src), str(original_dest))

    # Write metadata
    with open(item_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")

    return metadata


def main():
    parser = argparse.ArgumentParser(description="Auto-ingest files from ingest/ into staged/")
    parser.add_argument("--all", action="store_true", help="Process all files (default: 1)")
    parser.add_argument("--count", type=int, default=1, help="Number of files to process (default: 1)")
    parser.add_argument("--config", type=Path, default=None, help="Path to ingest_config.yaml")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config_path = args.config or (project_root / "tools" / "ingest_config.yaml")
    config = load_config(config_path)

    ingest_dir = project_root / config["ingest_dir"]
    staged_dir = project_root / config["staged_dir"]
    content_json = project_root / config["content_json"]

    if not ingest_dir.exists():
        ingest_dir.mkdir(parents=True)
        print(f"Created {ingest_dir}/. Drop files here and re-run.")
        return

    staged_dir.mkdir(parents=True, exist_ok=True)

    files = find_ingestable_files(ingest_dir)
    if not files:
        print(f"No supported files in {ingest_dir}/. Drop images or videos there first.")
        return

    count = len(files) if args.all else min(args.count, len(files))
    to_process = files[:count]

    print(f"Found {len(files)} file(s) in ingest/. Processing {count}.\n")

    for i, f in enumerate(to_process, 1):
        try:
            meta = process_file(
                f,
                content_json=content_json,
                staged_dir=staged_dir,
                max_width=config["max_image_width"],
                quality=config["image_quality"],
                max_video_duration=config["max_video_duration_sec"],
                max_video_size_mb=config["max_video_file_mb"],
            )
            print(f"  [{i}/{count}] {f.name} → {meta['id']} ({meta['media_type']})")
        except Exception as e:
            print(f"  [{i}/{count}] {f.name} — ERROR: {e}")

    remaining = len(files) - count
    print(f"\nDone. {count} item(s) staged.")
    if remaining > 0:
        print(f"{remaining} file(s) remaining in ingest/.")
    print("\nNext step: ask Claude Code to analyze staged items, then run:")
    print("  python tools/review_staged.py")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tools/test_auto_ingest.py -v
```

Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/auto_ingest.py tests/tools/test_auto_ingest.py
git commit -m "feat: add auto-ingest CLI for processing files into staged/"
```

---

### Task 6: Review CLI — `tools/review_staged.py`

**Files:**
- Create: `tools/review_staged.py`

- [ ] **Step 1: Write test for staged item discovery and metadata loading**

Create `tests/tools/test_review_staged.py`:

```python
import json
import pytest
from pathlib import Path
from tools.review_staged import find_pending_items, load_staged_metadata, save_staged_metadata


@pytest.fixture
def staged_item(tmp_project):
    """Create a staged item with full metadata."""
    item_dir = tmp_project / "staged" / "img-002"
    item_dir.mkdir(parents=True)
    meta = {
        "id": "img-002",
        "media_type": "image",
        "original_filename": "photo.jpg",
        "file_size_kb": 200,
        "dimensions": "1200x800",
        "is_ai": {"value": True, "confidence": "high", "source": "claude-vision"},
        "category": {"value": "landscape", "source": "claude-vision"},
        "source": None,
        "attribution": None,
        "license": None,
        "explanation": {"value": "Draft explanation...", "source": "claude-vision"},
        "generation_method": {"value": "stable-diffusion", "source": "claude-vision"},
        "prior_difficulty": None,
        "tags": {"value": ["mountain", "sunset"], "source": "claude-vision"},
        "exif": {"camera": None, "software": "Stable Diffusion", "date": None},
        "auto_ingest_date": "2026-03-29T10:00:00+00:00",
        "review_status": "pending",
    }
    (item_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    return item_dir


class TestFindPendingItems:
    def test_finds_pending(self, tmp_project, staged_item):
        items = find_pending_items(tmp_project / "staged")
        assert len(items) == 1
        assert items[0].name == "img-002"

    def test_skips_approved(self, tmp_project, staged_item):
        meta_path = staged_item / "metadata.json"
        meta = json.loads(meta_path.read_text())
        meta["review_status"] = "approved"
        meta_path.write_text(json.dumps(meta))
        items = find_pending_items(tmp_project / "staged")
        assert len(items) == 0

    def test_empty_staged(self, tmp_project):
        items = find_pending_items(tmp_project / "staged")
        assert len(items) == 0


class TestMetadataIO:
    def test_load_and_save_roundtrip(self, staged_item):
        meta = load_staged_metadata(staged_item)
        assert meta["id"] == "img-002"
        meta["review_status"] = "approved"
        save_staged_metadata(staged_item, meta)
        reloaded = load_staged_metadata(staged_item)
        assert reloaded["review_status"] == "approved"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_review_staged.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `tools/review_staged.py`**

```python
#!/usr/bin/env python3
"""Stage 2: Interactive CLI review of staged items."""

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LICENSE_OPTIONS = [
    "CC0-1.0",
    "CC-BY-4.0",
    "CC-BY-SA-4.0",
    "Unsplash License",
    "Pexels License",
    "MIT",
    "Other (type it)",
]

DIFFICULTY_GUIDE = """
  0.0-0.2  Very easy — almost everyone gets it right
  0.2-0.4  Easy — most players get it right
  0.4-0.6  Medium — about half get it right
  0.6-0.8  Hard — most players get it wrong
  0.8-1.0  Very hard — almost everyone gets it wrong"""


def find_pending_items(staged_dir: Path, include_all: bool = False) -> list[Path]:
    """Return staged item directories filtered by review_status."""
    items = []
    if not staged_dir.exists():
        return items
    for d in sorted(staged_dir.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        if not meta_path.exists():
            continue
        if include_all:
            items.append(d)
        else:
            meta = json.loads(meta_path.read_text())
            if meta.get("review_status") == "pending":
                items.append(d)
    return items


def load_staged_metadata(item_dir: Path) -> dict:
    """Load metadata.json from a staged item directory."""
    with open(item_dir / "metadata.json") as f:
        return json.load(f)


def save_staged_metadata(item_dir: Path, meta: dict) -> None:
    """Save metadata.json to a staged item directory."""
    with open(item_dir / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


def open_media(item_dir: Path, meta: dict) -> None:
    """Open the media file in the default viewer."""
    item_id = meta["id"]
    # Find the media file (not original, not thumbnail, not metadata)
    for f in item_dir.iterdir():
        if f.name.startswith(item_id) and f.suffix in (".jpg", ".jpeg", ".png", ".mp4", ".webm", ".mov"):
            if platform.system() == "Darwin":
                subprocess.Popen(["open", str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif platform.system() == "Linux":
                subprocess.Popen(["xdg-open", str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return


def display_value(val):
    """Format a metadata value for display, handling both raw and source-tagged values."""
    if val is None:
        return "___"
    if isinstance(val, dict) and "value" in val:
        confidence = f", {val['confidence']} confidence" if "confidence" in val else ""
        source = val.get("source", "unknown")
        v = val["value"]
        if isinstance(v, list):
            v = ", ".join(v)
        return f"{v}  [{source}{confidence}]"
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


def extract_value(val):
    """Get the raw value from a possibly source-tagged field."""
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


def prompt_field(field_name: str, current_val, meta: dict) -> any:
    """Prompt the user for a field value. Returns the new value."""
    display = display_value(current_val)

    if field_name == "license" and current_val is None:
        print(f"\n  {field_name}: {display}")
        print("  Choose a license:")
        for i, lic in enumerate(LICENSE_OPTIONS, 1):
            print(f"    {i}. {lic}")
        choice = input("  Enter number or type custom: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(LICENSE_OPTIONS):
            selected = LICENSE_OPTIONS[int(choice) - 1]
            if selected == "Other (type it)":
                return input("  License: ").strip()
            return selected
        return choice if choice else None

    if field_name == "prior_difficulty" and current_val is None:
        print(f"\n  {field_name}: {display}")
        print(DIFFICULTY_GUIDE)
        val = input("  Enter difficulty (0.0-1.0): ").strip()
        try:
            f = float(val)
            if 0.0 <= f <= 1.0:
                return f
            print("  Must be between 0.0 and 1.0")
            return None
        except ValueError:
            return None

    if current_val is not None:
        val = input(f"  {field_name}: {display}  [Enter=keep, or type new]: ").strip()
        if not val:
            return extract_value(current_val)
        # Handle special types
        if field_name == "is_ai":
            return val.lower() in ("true", "yes", "1", "y")
        if field_name == "tags":
            return [t.strip() for t in val.split(",")]
        if field_name == "prior_difficulty":
            try:
                return float(val)
            except ValueError:
                return extract_value(current_val)
        return val
    else:
        val = input(f"  {field_name}: {display}  → ").strip()
        if not val:
            return None
        if field_name == "is_ai":
            return val.lower() in ("true", "yes", "1", "y")
        if field_name == "prior_difficulty":
            try:
                return float(val)
            except ValueError:
                return None
        return val


def review_item(item_dir: Path, meta: dict) -> str:
    """Review a single staged item. Returns 'approved', 'skipped', or 'rejected'."""
    item_id = meta["id"]
    filename = meta.get("original_filename", "unknown")
    dims = meta.get("dimensions", "?")
    size_kb = meta.get("file_size_kb", "?")

    print(f"\n{'─' * 50}")
    print(f"  {item_id} ({filename})  {dims}  {size_kb}KB")
    print(f"{'─' * 50}")

    # Open media file
    open_media(item_dir, meta)

    # Show EXIF if available
    exif = meta.get("exif", {})
    exif_parts = []
    if exif.get("camera"):
        exif_parts.append(f"camera={exif['camera']}")
    if exif.get("software"):
        exif_parts.append(f"software={exif['software']}")
    if exif.get("date"):
        exif_parts.append(f"date={exif['date']}")
    if exif_parts:
        print(f"  EXIF: {', '.join(exif_parts)}")

    # Review fields in order
    review_fields = [
        "is_ai", "category", "source", "generation_method",
        "tags", "explanation", "attribution", "license", "prior_difficulty",
    ]

    values = {}
    for field in review_fields:
        current = meta.get(field)
        values[field] = prompt_field(field, current, meta)

    # Show summary
    print(f"\n{'─' * 30} Summary {'─' * 30}")
    for field in review_fields:
        v = values[field]
        if isinstance(v, list):
            v = ", ".join(v)
        print(f"  {field:20s} {v}")

    # Ask for decision
    while True:
        choice = input("\n  [a]pprove / [e]dit field / [s]kip / [r]eject: ").strip().lower()
        if choice == "a":
            for field in review_fields:
                meta[field] = values[field]
            meta["review_status"] = "approved"
            save_staged_metadata(item_dir, meta)
            print(f"  ✓ {item_id} approved")
            return "approved"
        elif choice == "e":
            field = input(f"  Which field? ({', '.join(review_fields)}): ").strip()
            if field in review_fields:
                values[field] = prompt_field(field, values[field], meta)
            else:
                print(f"  Unknown field: {field}")
        elif choice == "s":
            print(f"  → {item_id} skipped")
            return "skipped"
        elif choice == "r":
            meta["review_status"] = "rejected"
            save_staged_metadata(item_dir, meta)
            print(f"  ✗ {item_id} rejected")
            return "rejected"


def main():
    parser = argparse.ArgumentParser(description="Review staged items interactively")
    parser.add_argument("--all", action="store_true", help="Show all items, not just pending")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    staged_dir = project_root / "staged"

    items = find_pending_items(staged_dir, include_all=args.all)
    if not items:
        status = "any" if args.all else "pending"
        print(f"No {status} items in staged/.")
        return

    print(f"Found {len(items)} item(s) to review.\n")

    counts = {"approved": 0, "skipped": 0, "rejected": 0}
    for item_dir in items:
        meta = load_staged_metadata(item_dir)
        result = review_item(item_dir, meta)
        counts[result] += 1

    print(f"\nReview complete: {counts['approved']} approved, "
          f"{counts['skipped']} skipped, {counts['rejected']} rejected.")
    if counts["approved"] > 0:
        print("\nNext step: python tools/promote.py")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tools/test_review_staged.py -v
```

Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/review_staged.py tests/tools/test_review_staged.py
git commit -m "feat: add interactive review CLI for staged items"
```

---

### Task 7: Promote CLI — `tools/promote.py`

**Files:**
- Create: `tools/promote.py`

- [ ] **Step 1: Write tests for promotion logic**

Create `tests/tools/test_promote.py`:

```python
import json
import pytest
from pathlib import Path
from PIL import Image
from tools.promote import find_approved_items, promote_item, flatten_metadata


@pytest.fixture
def approved_item(tmp_project):
    """Create an approved staged item with media file."""
    item_dir = tmp_project / "staged" / "img-002"
    item_dir.mkdir(parents=True)
    # Create a media file
    img = Image.new("RGB", (1200, 800), color=(100, 100, 100))
    img.save(str(item_dir / "img-002.jpg"), "JPEG")
    # Create original
    img.save(str(item_dir / "original.jpg"), "JPEG")
    # Create metadata
    meta = {
        "id": "img-002",
        "media_type": "image",
        "original_filename": "photo.jpg",
        "file_size_kb": 200,
        "dimensions": "1200x800",
        "is_ai": True,
        "category": "landscape",
        "source": "Stable Diffusion XL",
        "attribution": "Generated by curator",
        "license": "CC0-1.0",
        "explanation": "The mountains show unnaturally smooth gradients.",
        "generation_method": "stable-diffusion",
        "prior_difficulty": 0.7,
        "tags": ["mountain", "sunset"],
        "exif": {"camera": None, "software": "Stable Diffusion", "date": None},
        "auto_ingest_date": "2026-03-29T10:00:00+00:00",
        "review_status": "approved",
    }
    (item_dir / "metadata.json").write_text(json.dumps(meta, indent=2))
    return item_dir


class TestFindApprovedItems:
    def test_finds_approved(self, tmp_project, approved_item):
        items = find_approved_items(tmp_project / "staged")
        assert len(items) == 1

    def test_skips_pending(self, tmp_project, approved_item):
        meta_path = approved_item / "metadata.json"
        meta = json.loads(meta_path.read_text())
        meta["review_status"] = "pending"
        meta_path.write_text(json.dumps(meta))
        items = find_approved_items(tmp_project / "staged")
        assert len(items) == 0


class TestFlattenMetadata:
    def test_strips_internal_fields(self, approved_item):
        meta = json.loads((approved_item / "metadata.json").read_text())
        flat = flatten_metadata(meta)
        assert "exif" not in flat
        assert "review_status" not in flat
        assert "auto_ingest_date" not in flat
        assert "original_filename" not in flat
        assert "file_size_kb" not in flat
        assert "dimensions" not in flat

    def test_keeps_production_fields(self, approved_item):
        meta = json.loads((approved_item / "metadata.json").read_text())
        flat = flatten_metadata(meta)
        assert flat["id"] == "img-002"
        assert flat["is_ai"] is True
        assert flat["category"] == "landscape"
        assert flat["tags"] == ["mountain", "sunset"]

    def test_unwraps_source_tagged_values(self):
        meta = {
            "id": "img-003",
            "media_type": "image",
            "is_ai": {"value": True, "confidence": "high", "source": "claude-vision"},
            "category": {"value": "animal", "source": "claude-vision"},
            "tags": {"value": ["cat"], "source": "claude-vision"},
            "source": "Test",
            "attribution": "Test",
            "license": "CC0-1.0",
            "explanation": {"value": "A cat.", "source": "claude-vision"},
            "generation_method": "photograph",
            "prior_difficulty": 0.5,
            "review_status": "approved",
            "exif": {},
            "auto_ingest_date": "2026-01-01",
            "original_filename": "cat.jpg",
            "file_size_kb": 100,
            "dimensions": "800x600",
        }
        flat = flatten_metadata(meta)
        assert flat["is_ai"] is True
        assert flat["category"] == "animal"
        assert flat["tags"] == ["cat"]
        assert flat["explanation"] == "A cat."


class TestPromoteItem:
    def test_copies_to_assets_and_updates_content(self, tmp_project, approved_item):
        content = json.loads((tmp_project / "content.json").read_text())
        assert len(content["items"]) == 1

        promote_item(
            approved_item,
            assets_dir=tmp_project / "assets",
            content_json=tmp_project / "content.json",
        )

        # Asset exists
        assert (tmp_project / "assets" / "img-002.jpg").exists()

        # content.json updated
        content = json.loads((tmp_project / "content.json").read_text())
        assert len(content["items"]) == 2
        new_item = content["items"][1]
        assert new_item["id"] == "img-002"
        assert new_item["url"] == "assets/img-002.jpg"
        assert "exif" not in new_item
        assert "review_status" not in new_item

        # Staged directory removed
        assert not approved_item.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tools/test_promote.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `tools/promote.py`**

```python
#!/usr/bin/env python3
"""Stage 3: Promote approved items from staged/ to assets/ + content.json."""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.content import load_content, save_content

PRODUCTION_FIELDS = [
    "id", "media_type", "url", "is_ai", "source", "attribution",
    "license", "explanation", "category", "generation_method",
    "prior_difficulty", "tags",
]

INTERNAL_FIELDS = {
    "exif", "review_status", "auto_ingest_date", "original_filename",
    "file_size_kb", "dimensions", "duration_sec",
}


def find_approved_items(staged_dir: Path) -> list[Path]:
    """Return staged item directories with review_status == 'approved'."""
    items = []
    if not staged_dir.exists():
        return items
    for d in sorted(staged_dir.iterdir()):
        if not d.is_dir():
            continue
        meta_path = d / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("review_status") == "approved":
            items.append(d)
    return items


def flatten_metadata(meta: dict) -> dict:
    """Convert staged metadata to production content.json format.

    Strips internal fields, unwraps source-tagged values.
    """
    flat = {}
    for field in PRODUCTION_FIELDS:
        if field == "url":
            continue  # Set by promote_item
        val = meta.get(field)
        # Unwrap source-tagged values
        if isinstance(val, dict) and "value" in val:
            val = val["value"]
        flat[field] = val
    return flat


def promote_item(item_dir: Path, assets_dir: Path, content_json: Path) -> dict:
    """Promote a single staged item to production. Returns the production item dict."""
    meta = json.loads((item_dir / "metadata.json").read_text())
    item_id = meta["id"]

    # Find the media file (named {id}.{ext})
    media_file = None
    for f in item_dir.iterdir():
        if f.name.startswith(item_id) and not f.name.endswith(".json"):
            media_file = f
            break

    if not media_file:
        raise FileNotFoundError(f"No media file found for {item_id} in {item_dir}")

    # Copy to assets/
    assets_dir.mkdir(parents=True, exist_ok=True)
    asset_dest = assets_dir / media_file.name
    shutil.copy2(str(media_file), str(asset_dest))

    # Build production item
    item = flatten_metadata(meta)
    item["url"] = f"assets/{media_file.name}"

    # Append to content.json
    content = load_content(content_json)
    content["items"].append(item)
    save_content(content_json, content)

    # Remove staged directory
    shutil.rmtree(item_dir)

    return item


def main():
    parser = argparse.ArgumentParser(description="Promote approved items to production")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    staged_dir = project_root / "staged"
    assets_dir = project_root / "assets"
    content_json = project_root / "content.json"

    items = find_approved_items(staged_dir)
    if not items:
        print("No approved items to promote.")
        return

    print(f"Found {len(items)} approved item(s):\n")
    summaries = []
    for item_dir in items:
        meta = json.loads((item_dir / "metadata.json").read_text())
        is_ai = meta.get("is_ai")
        if isinstance(is_ai, dict):
            is_ai = is_ai.get("value")
        ai_str = "AI" if is_ai else "Real"
        gen = meta.get("generation_method")
        if isinstance(gen, dict):
            gen = gen.get("value")
        diff = meta.get("prior_difficulty", "?")
        cat = meta.get("category")
        if isinstance(cat, dict):
            cat = cat.get("value")
        print(f"  {meta['id']}  {cat}  {ai_str} ({gen})  difficulty: {diff}")
        summaries.append(meta)

    choice = input("\nPromote all? [y/n/pick]: ").strip().lower()
    if choice == "n":
        print("Aborted.")
        return
    elif choice == "pick":
        selected = input("Enter IDs (comma-separated): ").strip()
        selected_ids = {s.strip() for s in selected.split(",")}
        items = [d for d in items if d.name in selected_ids]
        if not items:
            print("No matching items.")
            return

    promoted = 0
    for item_dir in items:
        try:
            item = promote_item(item_dir, assets_dir, content_json)
            print(f"  ✓ {item['id']} → assets/{item['id']}")
            promoted += 1
        except Exception as e:
            print(f"  ✗ {item_dir.name} — ERROR: {e}")

    content = load_content(content_json)
    ai_count = sum(1 for i in content["items"] if i.get("is_ai"))
    real_count = len(content["items"]) - ai_count

    # Calculate total assets size
    total_bytes = sum(f.stat().st_size for f in assets_dir.iterdir() if f.is_file())
    total_mb = total_bytes / (1024 * 1024)

    print(f"\nPromoted {promoted} item(s). content.json now has "
          f"{len(content['items'])} items ({ai_count} AI, {real_count} real).")
    print(f"Assets: {sum(1 for f in assets_dir.iterdir() if f.is_file())} files, {total_mb:.1f} MB total.")
    print(f"\nNext: git add assets/ content.json && git commit && git push")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/tools/test_promote.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/promote.py tests/tools/test_promote.py
git commit -m "feat: add promote CLI to move approved items to production"
```

---

### Task 8: Migration script — `tools/migrate_existing.py`

**Files:**
- Create: `tools/migrate_existing.py`

- [ ] **Step 1: Implement `tools/migrate_existing.py`**

```python
#!/usr/bin/env python3
"""One-time migration: download Unsplash images to assets/, update content.json URLs,
remove placeholder items."""

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.lib.content import load_content, save_content
from tools.lib.files import optimize_image


def main():
    project_root = Path(__file__).resolve().parent.parent
    content_json = project_root / "content.json"
    assets_dir = project_root / "assets"
    assets_dir.mkdir(exist_ok=True)

    content = load_content(content_json)
    items = content["items"]

    # Separate real items (with Unsplash URLs) from placeholders
    real_items = []
    placeholder_items = []
    for item in items:
        if "PLACEHOLDER" in item.get("url", ""):
            placeholder_items.append(item)
        else:
            real_items.append(item)

    print(f"Found {len(real_items)} real items to migrate, "
          f"{len(placeholder_items)} placeholders to remove.\n")

    # Download and optimize real items
    migrated = []
    for item in real_items:
        item_id = item["id"]
        url = item["url"]
        print(f"  Downloading {item_id} from {url[:60]}...")

        # Download to temp file
        tmp_path = assets_dir / f"{item_id}_tmp.jpg"
        try:
            urllib.request.urlretrieve(url, str(tmp_path))
        except Exception as e:
            print(f"    ERROR: {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            continue

        # Optimize
        final_path = assets_dir / f"{item_id}.jpg"
        optimize_image(tmp_path, final_path, max_width=1200, quality=85)
        tmp_path.unlink()

        size_kb = final_path.stat().st_size / 1024
        print(f"    → assets/{item_id}.jpg ({size_kb:.0f} KB)")

        item["url"] = f"assets/{item_id}.jpg"
        migrated.append(item)

    # Update content.json: keep only migrated items
    content["items"] = migrated
    save_content(content_json, content)

    print(f"\nMigration complete:")
    print(f"  {len(migrated)} items migrated to assets/")
    print(f"  {len(placeholder_items)} placeholder items removed")
    print(f"  content.json updated ({len(migrated)} items)")
    print(f"\nNext: git add assets/ content.json && git commit && git push")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run migration (manual verification)**

```bash
python tools/migrate_existing.py
```

Expected output: 10 images downloaded, 10 placeholders removed, content.json updated.

- [ ] **Step 3: Verify assets and content.json**

```bash
ls -la assets/
python -c "import json; c=json.load(open('content.json')); print(f'{len(c[\"items\"])} items, all URLs local:', all(i['url'].startswith('assets/') for i in c['items']))"
```

Expected: 10 jpg files in assets/, content.json has 10 items, all URLs start with `assets/`.

- [ ] **Step 4: Commit**

```bash
git add tools/migrate_existing.py assets/ content.json
git commit -m "feat: migrate Unsplash content to local assets, remove placeholders"
```

---

### Task 9: Update .gitignore, index.html, and documentation

**Files:**
- Modify: `index.html` (update content.json URL handling for relative `assets/` paths)
- Modify: `docs/content-guide.md` (document ingest pipeline)
- Create: `tools/README.md`

- [ ] **Step 1: Create `tools/README.md`**

```markdown
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

This extracts EXIF data, optimizes images, creates video thumbnails, and stages items in `staged/`.

### 3. Vision analysis (Claude Code)

Ask Claude Code to analyze the staged items. It will read each image and fill in metadata fields (is_ai, category, tags, explanation, generation_method).

### 4. Review

```bash
python tools/review_staged.py        # Review pending items
python tools/review_staged.py --all  # Re-review all items
```

Interactive CLI walkthrough. Fill in source, attribution, license, difficulty. Approve, skip, or reject each item.

### 5. Promote

```bash
python tools/promote.py
```

Moves approved items to `assets/` and appends to `content.json`. Does not auto-commit.

### 6. Commit and push

```bash
git add assets/ content.json
git commit -m "feat: add new content items"
git push
```
```

- [ ] **Step 2: Verify the full pipeline end-to-end with a test image**

```bash
# Create a test image in ingest/
python -c "from PIL import Image; Image.new('RGB', (2000,1500), (200,100,50)).save('ingest/test_e2e.jpg')"

# Auto-ingest
python tools/auto_ingest.py

# Check staged output
ls staged/
cat staged/img-*/metadata.json
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/tools/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tools/README.md docs/content-guide.md
git commit -m "docs: add ingest pipeline README and update content guide"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Scaffolding, config, fixtures | conftest.py |
| 2 | content.py (JSON R/W, ID gen) | test_content.py |
| 3 | extract.py (EXIF, file detect, video probe) | test_extract.py |
| 4 | files.py (image optimize, video thumbnails) | test_files.py |
| 5 | auto_ingest.py CLI | test_auto_ingest.py |
| 6 | review_staged.py CLI | test_review_staged.py |
| 7 | promote.py CLI | test_promote.py |
| 8 | migrate_existing.py (one-time) | Manual verification |
| 9 | Documentation + E2E verification | Full suite |
