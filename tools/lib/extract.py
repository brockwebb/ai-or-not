"""File type detection, EXIF extraction, and video probing."""

import subprocess
import json
from pathlib import Path

from PIL import Image
from PIL.ExifTags import TAGS

SUPPORTED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SUPPORTED_VIDEO_EXT = {".mp4", ".webm", ".mov"}


def detect_media_type(path: Path) -> str:
    """Return 'image' or 'video' based on file extension. Raises ValueError if unsupported."""
    ext = path.suffix.lower()
    if ext in SUPPORTED_IMAGE_EXT:
        return "image"
    if ext in SUPPORTED_VIDEO_EXT:
        return "video"
    raise ValueError(f"Unsupported file type: {ext} ({path.name})")


def extract_exif(path: Path) -> dict:
    """Extract EXIF metadata from an image. Returns dict with camera, software, date."""
    result = {"camera": None, "software": None, "date": None}
    try:
        with Image.open(path) as img:
            exif_data = img._getexif()
            if not exif_data:
                return result
            decoded = {TAGS.get(k, k): v for k, v in exif_data.items()}
            result["camera"] = decoded.get("Model")
            result["software"] = decoded.get("Software")
            date_val = decoded.get("DateTimeOriginal") or decoded.get("DateTime")
            if date_val:
                result["date"] = str(date_val)
    except Exception:
        pass
    return result


def probe_video(path: Path) -> dict:
    """Probe a video file for duration, dimensions, and file size using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path.name}: {proc.stderr}")

    info = json.loads(proc.stdout)

    video_stream = None
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise RuntimeError(f"No video stream found in {path.name}")

    duration = float(info.get("format", {}).get("duration", 0))
    file_size_mb = path.stat().st_size / (1024 * 1024)

    return {
        "duration_sec": duration,
        "width": int(video_stream.get("width", 0)),
        "height": int(video_stream.get("height", 0)),
        "file_size_mb": round(file_size_mb, 2),
    }
