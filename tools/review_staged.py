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

    open_media(item_dir, meta)

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

    review_fields = [
        "is_ai", "category", "source", "generation_method",
        "tags", "explanation", "attribution", "license", "prior_difficulty",
    ]

    values = {}
    for field in review_fields:
        current = meta.get(field)
        values[field] = prompt_field(field, current, meta)

    print(f"\n{'─' * 30} Summary {'─' * 30}")
    for field in review_fields:
        v = values[field]
        if isinstance(v, list):
            v = ", ".join(v)
        print(f"  {field:20s} {v}")

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
