"""FFmpeg command construction and video assembly utilities.

Handles:
- Aspect ratio scaling & padding (9:16 vertical and 16:9 horizontal) without stretching.
- Sidechain ducking of background music beneath narration.
- Loudness normalization (EBU R128).
- Subtitle generation (SRT) and overlay.
- End-card generation for AI disclosure.
"""

from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, List, Optional
from pipeline.config import get_config


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is found in system PATH or configured path."""
    cfg = get_config().ffmpeg
    return bool(shutil.which(cfg.ffmpeg_path))


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp format: HH:MM:SS,mmm."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    msecs = int(round((seconds - int(seconds)) * 1000))
    if msecs >= 1000:
        msecs = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"


def generate_srt(shots: List[Dict[str, Any]], output_path: str | Path) -> Path:
    """Generate an SRT subtitle file from shots using english_translation."""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    current_time = 0.0
    lines = []
    index = 1

    for shot in shots:
        duration = float(shot.get("duration", 7.5))
        translation = shot.get("english_translation", "").strip()
        start_ts = format_srt_timestamp(current_time)
        end_ts = format_srt_timestamp(current_time + duration)

        if translation:
            lines.append(f"{index}\n{start_ts} --> {end_ts}\n{translation}\n")
            index += 1
        current_time += duration

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def build_audio_ducking_filter(
    narration_input_index: int = 1,
    music_input_index: int = 2,
    ducking_attenuation_db: float = -14.0,
) -> str:
    """Construct FFmpeg complex audio filter graph with sidechain compression ducking.

    Ducks background music whenever narration is speaking and normalizes with loudnorm.
    """
    ratio = 4.0
    threshold = 0.125
    filter_graph = (
        f"[{music_input_index}:a]volume=0.35[bgm];"
        f"[bgm][{narration_input_index}:a]sidechaincompress="
        f"threshold={threshold}:ratio={ratio}:attack=20:release=300[ducked];"
        f"[{narration_input_index}:a][ducked]amix=inputs=2:duration=first:dropout_transition=2,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )
    return filter_graph


def build_aspect_ratio_filter(aspect_ratio: str = "16:9") -> str:
    """Build scale/crop video filter for 16:9 or 9:16 avoiding stretching."""
    if aspect_ratio == "9:16":
        # Target 1080x1920 vertical format:
        # Scale preserving aspect ratio to fill vertical dimension, then crop center
        return (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,setsar=1"
        )
    elif aspect_ratio == "16:9":
        # Target 1920x1080 horizontal format:
        # Scale preserving aspect ratio to fit or crop center
        return (
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080:(in_w-1920)/2:(in_h-1080)/2,setsar=1"
        )
    elif aspect_ratio == "1:1":
        return (
            "scale=1080:1080:force_original_aspect_ratio=increase,"
            "crop=1080:1080:(in_w-1080)/2:(in_h-1080)/2,setsar=1"
        )
    else:
        raise ValueError(f"Unsupported aspect ratio: {aspect_ratio}")


def build_end_card_command(
    title: str,
    disclosure_text: str,
    duration: float,
    output_video_path: str | Path,
    aspect_ratio: str = "16:9",
    bg_color: str = "black",
    font_color: str = "white",
) -> List[str]:
    """Construct FFmpeg command to generate the AI disclosure end card video clip."""
    ffmpeg_bin = get_config().ffmpeg.ffmpeg_path
    width, height = (1920, 1080) if aspect_ratio == "16:9" else (1080, 1920)

    # Clean text for drawtext filter escaping
    safe_title = title.replace("'", "").replace(":", r"\:")
    safe_text = disclosure_text.replace("'", "").replace(":", r"\:")

    drawtext_title = (
        f"drawtext=text='{safe_title}':fontcolor={font_color}:fontsize={48 if aspect_ratio=='16:9' else 40}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-80"
    )
    drawtext_desc = (
        f"drawtext=text='{safe_text}':fontcolor={font_color}:fontsize={24 if aspect_ratio=='16:9' else 20}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+20"
    )

    vf_filter = f"{drawtext_title},{drawtext_desc}"

    return [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi",
        "-i", f"color=c={bg_color}:s={width}x{height}:d={duration}:r=24",
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_video_path),
    ]


def build_video_concat_command(
    concat_list_file: str | Path,
    output_path: str | Path,
) -> List[str]:
    """Build FFmpeg concat demuxer command."""
    ffmpeg_bin = get_config().ffmpeg.ffmpeg_path
    return [
        ffmpeg_bin,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list_file),
        "-c", "copy",
        str(output_path),
    ]


def build_final_assembly_command(
    video_input_path: str | Path,
    narration_audio_path: str | Path,
    music_audio_path: str | Path,
    output_path: str | Path,
    aspect_ratio: str = "16:9",
    subtitles_srt_path: Optional[str | Path] = None,
    ducking_attenuation_db: float = -14.0,
) -> List[str]:
    """Construct full FFmpeg command for video, ducked audio mixing, and optional subtitles."""
    ffmpeg_bin = get_config().ffmpeg.ffmpeg_path
    
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(video_input_path),
        "-i", str(narration_audio_path),
        "-i", str(music_audio_path),
    ]

    video_filter = build_aspect_ratio_filter(aspect_ratio)
    if subtitles_srt_path and Path(subtitles_srt_path).exists():
        # Escape path for FFmpeg subtitles filter
        escaped_srt = str(subtitles_srt_path).replace("\\", "/").replace(":", r"\:")
        video_filter += f",subtitles='{escaped_srt}'"

    audio_filter = build_audio_ducking_filter(
        narration_input_index=1,
        music_input_index=2,
        ducking_attenuation_db=ducking_attenuation_db,
    )

    cmd.extend([
        "-filter_complex",
        f"[0:v]{video_filter}[vout];{audio_filter}",
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output_path),
    ])

    return cmd


def execute_ffmpeg(args: List[str]) -> subprocess.CompletedProcess:
    """Execute FFmpeg command synchronously."""
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
