"""
test_data.py — Generate synthetic JSONL and content.json for testing.

Creates sessions with known properties:
- Items with varying difficulty (some easy, some hard)
- A drift changepoint halfway through (accuracy drops)
- Varying player abilities
- Multiple categories and generation methods
"""

import argparse
import json
import logging
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# Item definitions with known difficulty levels.
# difficulty = P(player gets it wrong). Higher = harder.
TEST_ITEMS = [
    {"id": "img-001", "media_type": "image", "is_ai": True, "category": "faces",
     "generation_method": "stable-diffusion", "prior_difficulty": 0.3,
     "explanation": "AI-generated face with subtle asymmetry"},
    {"id": "img-002", "media_type": "image", "is_ai": False, "category": "faces",
     "generation_method": "real", "prior_difficulty": 0.2,
     "explanation": "Real photograph, natural lighting"},
    {"id": "img-003", "media_type": "image", "is_ai": True, "category": "landscapes",
     "generation_method": "midjourney", "prior_difficulty": 0.7,
     "explanation": "AI landscape, very realistic rendering"},
    {"id": "img-004", "media_type": "image", "is_ai": False, "category": "landscapes",
     "generation_method": "real", "prior_difficulty": 0.4,
     "explanation": "Real landscape that looks surreal"},
    {"id": "img-005", "media_type": "image", "is_ai": True, "category": "animals",
     "generation_method": "dall-e", "prior_difficulty": 0.5,
     "explanation": "AI-generated cat with extra toes"},
    {"id": "img-006", "media_type": "image", "is_ai": False, "category": "animals",
     "generation_method": "real", "prior_difficulty": 0.3,
     "explanation": "Real photo of a dog"},
    {"id": "img-007", "media_type": "image", "is_ai": True, "category": "text",
     "generation_method": "stable-diffusion", "prior_difficulty": 0.2,
     "explanation": "AI image with garbled text on signs"},
    {"id": "img-008", "media_type": "image", "is_ai": False, "category": "text",
     "generation_method": "real", "prior_difficulty": 0.1,
     "explanation": "Real photo with clear readable text"},
    {"id": "vid-001", "media_type": "video", "is_ai": True, "category": "faces",
     "generation_method": "deepfake", "prior_difficulty": 0.6,
     "explanation": "Deepfake video with slight lip-sync issues"},
    {"id": "vid-002", "media_type": "video", "is_ai": False, "category": "faces",
     "generation_method": "real", "prior_difficulty": 0.15,
     "explanation": "Real video interview"},
    {"id": "img-009", "media_type": "image", "is_ai": True, "category": "hands",
     "generation_method": "midjourney", "prior_difficulty": 0.35,
     "explanation": "AI image with six fingers"},
    {"id": "img-010", "media_type": "image", "is_ai": True, "category": "landscapes",
     "generation_method": "dall-e", "prior_difficulty": 0.8,
     "explanation": "AI landscape nearly indistinguishable from real"},
    {"id": "img-011", "media_type": "image", "is_ai": False, "category": "hands",
     "generation_method": "real", "prior_difficulty": 0.25,
     "explanation": "Real photo of hands"},
    {"id": "img-012", "media_type": "image", "is_ai": True, "category": "faces",
     "generation_method": "stable-diffusion", "prior_difficulty": 0.55,
     "explanation": "AI face, photorealistic but earrings don't match"},
    {"id": "img-013", "media_type": "image", "is_ai": False, "category": "animals",
     "generation_method": "real", "prior_difficulty": 0.45,
     "explanation": "Real photo that looks AI-generated due to odd colors"},
    {"id": "img-014", "media_type": "image", "is_ai": True, "category": "text",
     "generation_method": "midjourney", "prior_difficulty": 0.25,
     "explanation": "AI image with nonsense text"},
    {"id": "img-015", "media_type": "image", "is_ai": False, "category": "landscapes",
     "generation_method": "real", "prior_difficulty": 0.6,
     "explanation": "HDR photograph that looks synthetic"},
]

# True difficulty used for simulation (not the prior — the actual ground truth).
# This lets us test calibration analysis too.
TRUE_DIFFICULTY = {
    "img-001": 0.25, "img-002": 0.15, "img-003": 0.75, "img-004": 0.50,
    "img-005": 0.45, "img-006": 0.20, "img-007": 0.15, "img-008": 0.10,
    "vid-001": 0.65, "vid-002": 0.10, "img-009": 0.30, "img-010": 0.85,
    "img-011": 0.20, "img-012": 0.50, "img-013": 0.55, "img-014": 0.20,
    "img-015": 0.65,
}

ITEMS_PER_SESSION = 10

REASONING_TEMPLATES = [
    "The hands looked weird",
    "Too perfect lighting",
    "Shadows don't match",
    "Text is garbled",
    "Looks too smooth",
    "Natural imperfections visible",
    "Background is blurry in a weird way",
    "Earrings are different",
    "Just a gut feeling",
    "",  # some players don't provide reasoning
    "",
    "Eyes look dead",
    "Skin texture is off",
    "This looks real to me",
]


def generate_session(
    session_num: int,
    total_sessions: int,
    base_time: datetime,
    items: list[dict],
    rng: np.random.Generator,
) -> dict:
    """Generate one synthetic session.

    Introduces a drift effect: sessions in the second half have lower
    player ability (simulating harder-to-detect AI content or different
    player population).

    Parameters
    ----------
    session_num : int
        Index of this session (0-based).
    total_sessions : int
        Total number of sessions being generated.
    base_time : datetime
        Start timestamp for the dataset.
    items : list[dict]
        Full item catalog.
    rng : np.random.Generator
        Random number generator for reproducibility.

    Returns
    -------
    dict
        Session object matching the JSONL schema.
    """
    session_id = uuid.uuid4().hex[:12]
    timestamp = base_time + timedelta(hours=session_num * 2, minutes=int(rng.integers(0, 60)))

    # Player ability: normally distributed, shifted down after midpoint (drift)
    midpoint = total_sessions // 2
    if session_num < midpoint:
        ability = rng.normal(loc=0.7, scale=0.2)
    else:
        # After drift: players are effectively worse (or AI is better)
        ability = rng.normal(loc=0.5, scale=0.2)

    ability = np.clip(ability, 0.05, 0.95)

    # Select random subset of items for this session
    selected = rng.choice(items, size=min(ITEMS_PER_SESSION, len(items)), replace=False)

    item_responses = []
    correct_count = 0

    for item in selected:
        item_id = item["id"]
        true_diff = TRUE_DIFFICULTY.get(item_id, 0.5)

        # P(correct) = ability * (1 - true_difficulty)
        # Simplified model: higher ability and lower difficulty → more likely correct
        p_correct = ability * (1.0 - true_diff) + (1.0 - ability) * true_diff * 0.3
        p_correct = np.clip(p_correct, 0.05, 0.95)

        is_correct = rng.random() < p_correct
        if is_correct:
            correct_count += 1

        reasoning = rng.choice(REASONING_TEMPLATES) if rng.random() > 0.3 else ""

        item_responses.append(
            {
                "item_id": item_id,
                "guess": bool(is_correct),  # Simplified: guess matches correctness
                "correct": bool(is_correct),
                "reasoning": reasoning,
            }
        )

    return {
        "session_id": session_id,
        "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "items": item_responses,
        "score": correct_count,
        "total": len(item_responses),
    }


def generate_content_json(items: list[dict]) -> list[dict]:
    """Build a full content.json from the test item definitions.

    Adds placeholder fields that would exist in the real content.json.
    """
    content = []
    for item in items:
        content.append(
            {
                "id": item["id"],
                "url": f"https://example.com/media/{item['id']}.jpg",
                "media_type": item["media_type"],
                "is_ai": item["is_ai"],
                "source": "synthetic-test-data",
                "attribution": "Test data generator",
                "license": "CC0",
                "explanation": item["explanation"],
                "category": item["category"],
                "generation_method": item["generation_method"],
                "prior_difficulty": item["prior_difficulty"],
                "tags": [item["category"], item["generation_method"]],
            }
        )
    return content


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic test data for AI or Not? analysis"
    )
    parser.add_argument(
        "--sessions",
        type=int,
        default=200,
        help="Number of sessions to generate (default: 200)",
    )
    parser.add_argument(
        "--output",
        default="test_sessions.jsonl",
        help="Output JSONL file path (default: test_sessions.jsonl)",
    )
    parser.add_argument(
        "--content-output",
        default="test_content.json",
        help="Output content.json path (default: test_content.json)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    rng = np.random.default_rng(args.seed)
    base_time = datetime(2026, 4, 1, 9, 0, 0)

    # Generate sessions
    sessions = []
    for i in range(args.sessions):
        session = generate_session(i, args.sessions, base_time, TEST_ITEMS, rng)
        sessions.append(session)

    # Write JSONL
    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        for session in sessions:
            f.write(json.dumps(session) + "\n")
    logger.info("Wrote %d sessions to %s", len(sessions), output_path)

    # Write content.json
    content = generate_content_json(TEST_ITEMS)
    content_path = Path(args.content_output)
    with open(content_path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2)
    logger.info("Wrote %d items to %s", len(content), content_path)

    # Print summary
    print(f"\n=== Test Data Generated ===")
    print(f"Sessions: {len(sessions)}")
    print(f"Items in catalog: {len(TEST_ITEMS)}")
    print(f"Items per session: {ITEMS_PER_SESSION}")
    print(f"Drift changepoint: session {args.sessions // 2}")
    print(f"Output: {output_path}")
    print(f"Content: {content_path}")


if __name__ == "__main__":
    main()
