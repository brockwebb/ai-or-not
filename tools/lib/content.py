"""Read/write content.json and generate sequential item IDs."""

import json
import re
from datetime import date
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

    for item in content.get("items", []):
        m = pattern.match(item["id"])
        if m:
            max_num = max(max_num, int(m.group(1)))

    if staged_dir and staged_dir.is_dir():
        for entry in staged_dir.iterdir():
            if entry.is_dir():
                m = pattern.match(entry.name)
                if m:
                    max_num = max(max_num, int(m.group(1)))

    return f"{prefix}-{max_num + 1:03d}"
