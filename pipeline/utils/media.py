"""Media sanity checks.

Presence of a file proves nothing: earlier mock runs left 36-byte "MP4" files and silent WAVs that
passed an existence check. These helpers inspect content so placeholders can never be mistaken for
real model output.
"""

import json
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Optional

# A real encoded clip of several seconds is far larger than this. The old placeholder was 36 bytes.
MIN_VIDEO_BYTES = 20_000
MIN_AUDIO_BYTES = 100_000


def _ffprobe_duration(path: Path) -> Optional[float]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return None


def video_problem(path: str | Path) -> Optional[str]:
    """Return a reason the file is not a usable video, or None if it looks real."""
    p = Path(path)
    if not p.is_file():
        return "file does not exist"
    size = p.stat().st_size
    if size < MIN_VIDEO_BYTES:
        return f"only {size} bytes (placeholder or truncated)"
    dur = _ffprobe_duration(p)
    if dur is not None and dur <= 0.5:
        return f"duration {dur:.2f}s is too short"
    return None


def audio_problem(path: str | Path) -> Optional[str]:
    """Return a reason the file is not a usable audio track, or None if it looks real."""
    p = Path(path)
    if not p.is_file():
        return "file does not exist"
    size = p.stat().st_size
    if size < MIN_AUDIO_BYTES:
        return f"only {size} bytes (placeholder or truncated)"
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as wf:
                if wf.getnframes() == 0:
                    return "WAV has zero frames"
        except wave.Error as exc:
            return f"unreadable WAV: {exc}"
    return None


def is_real_video(path: str | Path) -> bool:
    return video_problem(path) is None


def is_real_audio(path: str | Path) -> bool:
    return audio_problem(path) is None
