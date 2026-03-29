import json
import shutil
import pytest
from pathlib import Path
from tools.auto_ingest import process_file, find_ingestable_files


class TestFindIngestableFiles:
    def test_finds_images(self, tmp_project, sample_image):
        shutil.copy(sample_image, tmp_project / "ingest" / "photo.jpg")
        files = find_ingestable_files(tmp_project / "ingest")
        assert len(files) == 1
        assert files[0].name == "photo.jpg"

    def test_ignores_unsupported(self, tmp_project):
        (tmp_project / "ingest" / "notes.txt").write_text("hello")
        files = find_ingestable_files(tmp_project / "ingest")
        assert len(files) == 0

    def test_empty_dir(self, tmp_project):
        files = find_ingestable_files(tmp_project / "ingest")
        assert len(files) == 0


class TestProcessFile:
    def test_processes_image(self, tmp_project, sample_image):
        src = tmp_project / "ingest" / "photo.jpg"
        shutil.copy(sample_image, src)

        result = process_file(
            src,
            content_json=tmp_project / "content.json",
            staged_dir=tmp_project / "staged",
            max_width=1200,
            quality=85,
        )

        assert result["id"] == "img-002"
        staged_dir = tmp_project / "staged" / "img-002"
        assert staged_dir.exists()
        assert (staged_dir / "img-002.jpg").exists()
        assert (staged_dir / "original.jpg").exists()

        meta = json.loads((staged_dir / "metadata.json").read_text())
        assert meta["id"] == "img-002"
        assert meta["media_type"] == "image"
        assert meta["original_filename"] == "photo.jpg"
        assert meta["review_status"] == "pending"
        assert meta["is_ai"] is None

        # Source file should be moved out of ingest/
        assert not src.exists()

    def test_processes_video(self, tmp_project, sample_video):
        src = tmp_project / "ingest" / "clip.mp4"
        shutil.copy(sample_video, src)

        result = process_file(
            src,
            content_json=tmp_project / "content.json",
            staged_dir=tmp_project / "staged",
            max_width=1200,
            quality=85,
        )

        assert result["id"] == "vid-001"
        staged_dir = tmp_project / "staged" / "vid-001"
        assert (staged_dir / "vid-001.mp4").exists()
        assert (staged_dir / "thumbnail.jpg").exists()
        assert (staged_dir / "original.mp4").exists()

        meta = json.loads((staged_dir / "metadata.json").read_text())
        assert meta["media_type"] == "video"
        assert "duration_sec" in meta
