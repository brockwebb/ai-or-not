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

    real_items = []
    placeholder_items = []
    for item in items:
        if "PLACEHOLDER" in item.get("url", ""):
            placeholder_items.append(item)
        else:
            real_items.append(item)

    print(f"Found {len(real_items)} real items to migrate, "
          f"{len(placeholder_items)} placeholders to remove.\n")

    migrated = []
    for item in real_items:
        item_id = item["id"]
        url = item["url"]
        print(f"  Downloading {item_id} from {url[:60]}...")

        tmp_path = assets_dir / f"{item_id}_tmp.jpg"
        try:
            urllib.request.urlretrieve(url, str(tmp_path))
        except Exception as e:
            print(f"    ERROR: {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            continue

        final_path = assets_dir / f"{item_id}.jpg"
        optimize_image(tmp_path, final_path, max_width=1200, quality=85)
        tmp_path.unlink()

        size_kb = final_path.stat().st_size / 1024
        print(f"    → assets/{item_id}.jpg ({size_kb:.0f} KB)")

        item["url"] = f"assets/{item_id}.jpg"
        migrated.append(item)

    content["items"] = migrated
    save_content(content_json, content)

    print(f"\nMigration complete:")
    print(f"  {len(migrated)} items migrated to assets/")
    print(f"  {len(placeholder_items)} placeholder items removed")
    print(f"  content.json updated ({len(migrated)} items)")
    print(f"\nNext: git add assets/ content.json && git commit && git push")


if __name__ == "__main__":
    main()
