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
