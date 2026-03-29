"""
load_data.py — Data loading utilities for AI or Not? analysis workbench.

Loads JSONL session exports and content.json into pandas DataFrames / dicts
suitable for downstream analysis scripts.
"""

import json
import logging
import sys
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def load_sessions(jsonl_path: str) -> pd.DataFrame:
    """Load JSONL session data and expand into per-item rows.

    Each row in the returned DataFrame represents one item-response
    (one player's guess on one item), not one session.

    Parameters
    ----------
    jsonl_path : str
        Path to the JSONL file. One JSON object per line, each representing
        a complete game session.

    Returns
    -------
    pd.DataFrame
        Columns: session_id, timestamp, item_id, guess, correct, reasoning,
                 score, total

    Raises
    ------
    FileNotFoundError
        If the JSONL file does not exist.
    """
    path = Path(jsonl_path)
    if not path.exists():
        raise FileNotFoundError(f"Session data file not found: {jsonl_path}")

    rows = []
    malformed_count = 0

    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                session = json.loads(line)
            except json.JSONDecodeError as e:
                malformed_count += 1
                logger.warning("Line %d: malformed JSON — %s", line_num, e)
                continue

            # Validate required top-level fields
            session_id = session.get("session_id")
            timestamp = session.get("timestamp")
            items = session.get("items")
            score = session.get("score")
            total = session.get("total")

            if session_id is None or items is None:
                malformed_count += 1
                logger.warning(
                    "Line %d: missing session_id or items field, skipping",
                    line_num,
                )
                continue

            if not isinstance(items, list):
                malformed_count += 1
                logger.warning(
                    "Line %d: 'items' is not a list, skipping", line_num
                )
                continue

            for item in items:
                if not isinstance(item, dict):
                    logger.warning(
                        "Line %d: item entry is not a dict, skipping item",
                        line_num,
                    )
                    continue

                rows.append(
                    {
                        "session_id": session_id,
                        "timestamp": timestamp,
                        "item_id": item.get("item_id"),
                        "guess": item.get("guess"),
                        "correct": item.get("correct"),
                        "reasoning": item.get("reasoning", ""),
                        "score": score,
                        "total": total,
                    }
                )

    if malformed_count > 0:
        logger.warning(
            "Skipped %d malformed line(s) in %s", malformed_count, jsonl_path
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "session_id",
            "timestamp",
            "item_id",
            "guess",
            "correct",
            "reasoning",
            "score",
            "total",
        ],
    )

    # Parse timestamps
    if not df.empty and df["timestamp"].notna().any():
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    return df


def load_content(json_path: str) -> dict:
    """Load content.json and return a dict keyed by item id.

    Parameters
    ----------
    json_path : str
        Path to content.json.

    Returns
    -------
    dict
        Keys are item id strings, values are the full item dicts from
        content.json.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Content file not found: {json_path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # content.json may be a list of items or a dict with an "items" key
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "items" in data:
        items = data["items"]
    else:
        raise ValueError(
            "content.json must be a list of items or a dict with an 'items' key"
        )

    content = {}
    for item in items:
        item_id = item.get("id")
        if item_id is None:
            logger.warning("Content item missing 'id' field, skipping: %s", item)
            continue
        content[item_id] = item

    return content


if __name__ == "__main__":
    # Quick smoke test when run directly
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("Usage: python load_data.py <sessions.jsonl> [content.json]")
        sys.exit(1)

    df = load_sessions(sys.argv[1])
    print(f"Loaded {len(df)} item-responses from {df['session_id'].nunique()} sessions")
    print(df.head())

    if len(sys.argv) >= 3:
        content = load_content(sys.argv[2])
        print(f"\nLoaded {len(content)} content items")
