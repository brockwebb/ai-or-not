import pytest
from PIL import Image
from tools.lib.files import optimize_image, extract_video_thumbnail, get_image_dimensions


class TestOptimizeImage:
    def test_resizes_wide_image(self, sample_image, tmp_path):
        out = tmp_path / "optimized.jpg"
        optimize_image(sample_image, out, max_width=1200, quality=85)
        with Image.open(out) as img:
            assert img.width == 1200
            assert img.height == 800

    def test_does_not_upscale_small_image(self, sample_png, tmp_path):
        out = tmp_path / "optimized.jpg"
        optimize_image(sample_png, out, max_width=1200, quality=85)
        with Image.open(out) as img:
            assert img.width == 800

    def test_converts_png_to_jpeg(self, sample_png, tmp_path):
        out = tmp_path / "optimized.jpg"
        optimize_image(sample_png, out, max_width=1200, quality=85)
        with Image.open(out) as img:
            assert img.format == "JPEG"
            assert img.mode == "RGB"


class TestExtractVideoThumbnail:
    def test_creates_thumbnail(self, sample_video, tmp_path):
        out = tmp_path / "thumb.jpg"
        extract_video_thumbnail(sample_video, out)
        assert out.exists()
        with Image.open(out) as img:
            assert img.width > 0
            assert img.height > 0


class TestGetImageDimensions:
    def test_returns_dimensions(self, sample_image):
        w, h = get_image_dimensions(sample_image)
        assert w == 2400
        assert h == 1600
