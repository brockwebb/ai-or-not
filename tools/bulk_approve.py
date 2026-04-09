#!/usr/bin/env python3
"""Bulk-approve staged items that already have complete metadata."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REQUIRED_FIELDS = [
    "is_ai",
    "category",
    "source",
    "generation_method",
    "tags",
    "prior_difficulty",
    "attribution",
    "license",
]


def extract_value(val):
    """Get the raw value from a possibly source-tagged field."""
    if isinstance(val, dict) and "value" in val:
        return val["value"]
    return val


def find_pending_items(staged_dir: Path) -> list[Path]:
    """Return staged item directories with review_status == 'pending'."""
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
        if meta.get("review_status") == "pending":
            items.append(d)
    return items


def check_completeness(meta: dict) -> list[str]:
    """Return list of missing required fields. Empty list means complete."""
    missing = []
    for field in REQUIRED_FIELDS:
        val = extract_value(meta.get(field))
        if val is None:
            missing.append(field)
        elif isinstance(val, list) and len(val) == 0:
            missing.append(field)
        elif isinstance(val, str) and val.strip() == "":
            missing.append(field)
    return missing


def main():
    parser = argparse.ArgumentParser(description="Bulk-approve staged items with complete metadata")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be approved without modifying anything")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    staged_dir = project_root / "staged"

    pending = find_pending_items(staged_dir)
    if not pending:
        print("No pending items in staged/.")
        return

    complete = []
    incomplete = []

    for item_dir in pending:
        meta = json.loads((item_dir / "metadata.json").read_text())
        missing = check_completeness(meta)
        if missing:
            incomplete.append((item_dir, meta, missing))
        else:
            complete.append((item_dir, meta))

    if complete:
        print(f"Found {len(complete)} items with complete metadata:\n")
        for item_dir, meta in complete:
            item_id = meta["id"]
            is_ai_val = extract_value(meta.get("is_ai"))
            ai_str = "AI  " if is_ai_val else "Real"
            category = extract_value(meta.get("category")) or "?"
            source = extract_value(meta.get("source")) or "?"
            print(f"  {item_id:<10}  {ai_str}  {category:<12}  {source}")
    else:
        print("No items with complete metadata found.")

    if incomplete:
        print(f"\n{len(incomplete)} item(s) have incomplete metadata (skipped):")
        for item_dir, meta, missing in incomplete:
            print(f"  {meta['id']:<10}  missing: {', '.join(missing)}")

    if not complete:
        return

    if args.dry_run:
        print(f"\n--dry-run: no changes made.")
        return

    print()
    choice = input(f"Approve all {len(complete)} complete items? [y/n]: ").strip().lower()
    if choice != "y":
        print("Aborted.")
        return

    for item_dir, meta in complete:
        meta["review_status"] = "approved"
        with open(item_dir / "metadata.json", "w") as f:
            json.dump(meta, f, indent=2)
            f.write("\n")

    print(f"  ✓ {len(complete)} items approved")
    print(f"\nNext step: python tools/promote.py")


if __name__ == "__main__":
    main()
