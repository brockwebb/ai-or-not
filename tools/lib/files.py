"""Image optimization, video thumbnails, and file dimension utilities."""

import subprocess
from pathlib import Path

from PIL import Image


def optimize_image(src: Path, dst: Path, max_width: int = 1200, quality: int = 85) -> None:
    """Resize image to max_width (preserving aspect ratio), convert to JPEG."""
    with Image.open(src) as img:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

        img.save(str(dst), "JPEG", quality=quality, optimize=True)


def extract_video_thumbnail(video_path: Path, out_path: Path) -> None:
    """Extract a frame from the middle of the video as a JPEG thumbnail."""
    duration_cmd = [
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
    ]
    proc = subprocess.run(duration_cmd, capture_output=True, text=True)
    duration = float(proc.stdout.strip()) if proc.returncode == 0 else 1.0
    midpoint = duration / 2

    cmd = [
        "ffmpeg", "-y", "-ss", str(midpoint), "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2", "-loglevel", "error", str(out_path)
    ]
    subprocess.run(cmd, check=True)


def get_image_dimensions(path: Path) -> tuple[int, int]:
    """Return (width, height) of an image file."""
    with Image.open(path) as img:
        return img.width, img.height
