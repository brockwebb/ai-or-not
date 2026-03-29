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
            continue
        val = meta.get(field)
        if isinstance(val, dict) and "value" in val:
            val = val["value"]
        flat[field] = val
    return flat


def promote_item(item_dir: Path, assets_dir: Path, content_json: Path) -> dict:
    """Promote a single staged item to production. Returns the production item dict."""
    meta = json.loads((item_dir / "metadata.json").read_text())
    item_id = meta["id"]

    media_file = None
    for f in item_dir.iterdir():
        if f.name.startswith(item_id) and not f.name.endswith(".json"):
            media_file = f
            break

    if not media_file:
        raise FileNotFoundError(f"No media file found for {item_id} in {item_dir}")

    assets_dir.mkdir(parents=True, exist_ok=True)
    asset_dest = assets_dir / media_file.name
    shutil.copy2(str(media_file), str(asset_dest))

    item = flatten_metadata(meta)
    item["url"] = f"assets/{media_file.name}"

    content = load_content(content_json)
    content["items"].append(item)
    save_content(content_json, content)

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

    total_bytes = sum(f.stat().st_size for f in assets_dir.iterdir() if f.is_file())
    total_mb = total_bytes / (1024 * 1024)

    print(f"\nPromoted {promoted} item(s). content.json now has "
          f"{len(content['items'])} items ({ai_count} AI, {real_count} real).")
    print(f"Assets: {sum(1 for f in assets_dir.iterdir() if f.is_file())} files, {total_mb:.1f} MB total.")
    print(f"\nNext: git add assets/ content.json && git commit && git push")


if __name__ == "__main__":
    main()
