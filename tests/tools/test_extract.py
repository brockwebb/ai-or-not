import pytest
from tools.lib.extract import detect_media_type, extract_exif, probe_video


class TestDetectMediaType:
    def test_jpg(self, sample_image):
        assert detect_media_type(sample_image) == "image"

    def test_png(self, sample_png):
        assert detect_media_type(sample_png) == "image"

    def test_mp4(self, sample_video):
        assert detect_media_type(sample_video) == "video"

    def test_unsupported_raises(self, tmp_path):
        txt = tmp_path / "notes.txt"
        txt.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported"):
            detect_media_type(txt)


class TestExtractExif:
    def test_returns_dict_for_jpeg(self, sample_image):
        exif = extract_exif(sample_image)
        assert isinstance(exif, dict)
        assert "camera" in exif
        assert "software" in exif
        assert "date" in exif

    def test_returns_empty_for_non_image(self, sample_video):
        exif = extract_exif(sample_video)
        assert exif["camera"] is None
        assert exif["software"] is None
        assert exif["date"] is None


class TestProbeVideo:
    def test_returns_duration_and_dimensions(self, sample_video):
        info = probe_video(sample_video)
        assert info["duration_sec"] == pytest.approx(3.0, abs=0.5)
        assert info["width"] == 640
        assert info["height"] == 480
        assert info["file_size_mb"] >= 0
