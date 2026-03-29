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
