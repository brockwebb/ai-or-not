import json
import os
import pytest
from PIL import Image


@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project directory structure for testing."""
    dirs = ["ingest", "staged", "assets", "data"]
    for d in dirs:
        (tmp_path / d).mkdir()

    content = {
        "version": "1.0.0",
        "meta": {
            "description": "Test content",
            "license": "MIT",
            "curator": "test",
            "last_updated": "2026-01-01",
        },
        "items": [
            {
                "id": "img-001",
                "media_type": "image",
                "url": "assets/img-001.jpg",
                "is_ai": False,
                "source": "Test",
                "attribution": "Test attribution",
                "license": "CC0-1.0",
                "explanation": "Test explanation",
                "category": "landscape",
                "generation_method": "photograph",
                "prior_difficulty": 0.5,
                "tags": ["test"],
            }
        ],
    }
    (tmp_path / "content.json").write_text(json.dumps(content, indent=2))
    return tmp_path


@pytest.fixture
def sample_image(tmp_path):
    """Create a sample JPEG image for testing."""
    img = Image.new("RGB", (2400, 1600), color=(100, 150, 200))
    path = tmp_path / "test_photo.jpg"
    img.save(str(path), "JPEG")
    return path


@pytest.fixture
def sample_png(tmp_path):
    """Create a sample PNG image for testing."""
    img = Image.new("RGBA", (800, 600), color=(50, 100, 150, 255))
    path = tmp_path / "ai_art.png"
    img.save(str(path), "PNG")
    return path


@pytest.fixture
def sample_video(tmp_path):
    """Create a minimal MP4 file for testing. Requires ffmpeg."""
    path = tmp_path / "clip.mp4"
    os.system(
        f'ffmpeg -y -f lavfi -i color=c=blue:s=640x480:d=3 '
        f'-c:v libx264 -pix_fmt yuv420p -loglevel error "{path}"'
    )
    if not path.exists():
        pytest.skip("ffmpeg not available for video test")
    return path
