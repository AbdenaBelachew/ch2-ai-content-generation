"""Audio helpers: make separately generated narration clips sound equally loud."""

import json
from pathlib import Path
import subprocess
from typing import Optional

from pipeline.config import get_config

TARGET_LUFS = -19.0   # narration level before the music mix (the final mix is loudnorm'd again)
TARGET_PEAK = -2.0


def _ffmpeg() -> str:
    return get_config().ffmpeg.ffmpeg_path


def measure_loudnorm(path: str | Path, prefilter: str = "") -> Optional[dict]:
    """First pass: EBU R128 measurements of a clip (optionally after prefilter). None if unmeasurable."""
    chain = (prefilter + "," if prefilter else "") + f"loudnorm=I={TARGET_LUFS}:TP={TARGET_PEAK}:LRA=11:print_format=json"
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-af", chain, "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    text = proc.stderr or ""
    start, end = text.rfind("{"), text.rfind("}")
    if proc.returncode != 0 or start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        if float(data["input_i"]) < -60:  # silence / unmeasurable
            return None
        return data
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def normalized_filter(measured: Optional[dict], prefilter: str = "") -> str:
    """Second-pass filter chain: a linear (transparent, no pumping) gain to the target loudness."""
    parts = [prefilter] if prefilter else []
    if measured:
        parts.append(
            f"loudnorm=I={TARGET_LUFS}:TP={TARGET_PEAK}:LRA=11:"
            f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
            f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}:linear=true"
        )
    return ",".join(parts)
