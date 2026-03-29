#!/usr/bin/env python3
"""Stage 1: Auto-ingest files from ingest/ into staged/ with metadata extraction."""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

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

    item_dir = staged_dir / item_id
    item_dir.mkdir(parents=True, exist_ok=True)

    ext = src.suffix.lower()
    if media_type == "image":
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
        metadata["exif"] = extract_exif(src)
    else:
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
