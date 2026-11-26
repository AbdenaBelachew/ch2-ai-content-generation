"""FFmpeg command construction and video assembly utilities.

Handles:
- Aspect ratio scaling & padding (9:16 vertical and 16:9 horizontal) without stretching.
- Sidechain ducking of background music beneath narration.
- Loudness normalization (EBU R128).
- Subtitle generation (SRT) and overlay.
- End-card generation for AI disclosure.
- Radio cut generation (scratch audio mix).
"""

import math
from pathlib import Path
import shutil
import struct
import subprocess
from typing import Any, Dict, List, Optional
import wave
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


def _wav_seconds(path: Path) -> Optional[float]:
    try:
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return None


def generate_srt(
    shots: List[Dict[str, Any]],
    output_path: str | Path,
    narration_dir: Optional[str | Path] = None,
    lead_in: float = 0.15,
) -> Path:
    """Generate an SRT from each shot's english_translation.

    With narration_dir, each caption is shown only while its line is spoken (from shot start +
    lead_in to the end of that shot's narration clip, never past the shot). Otherwise it fills the shot.
    """
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    current_time = 0.0
    lines = []
    index = 1

    for shot in shots:
        duration = float(shot.get("duration", 7.5))
        translation = shot.get("english_translation", "").strip()
        start = current_time
        end = current_time + duration
        if narration_dir is not None:
            spoken = _wav_seconds(Path(narration_dir) / f"{shot.get('shot_id', '')}.wav")
            if spoken:
                start = current_time + lead_in
                end = current_time + min(duration, lead_in + spoken)

        if translation:
            lines.append(f"{index}\n{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}\n{translation}\n")
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
    ratio = 8.0
    threshold = 0.08
    # Pad the narration with trailing silence so the sidechain stage (and the music) keep running
    # after the voice ends, e.g. through the end card.
    filter_graph = (
        f"[{narration_input_index}:a]apad=pad_dur=15,asplit=2[narr_mix][narr_key];"
        f"[{music_input_index}:a]volume=0.12[bgm];"
        f"[bgm][narr_key]sidechaincompress="
        f"threshold={threshold}:ratio={ratio}:attack=20:release=300[ducked];"
        f"[narr_mix][ducked]amix=inputs=2:duration=longest:dropout_transition=2,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )
    return filter_graph


def build_radio_cut_command(
    narration_audio_path: str | Path,
    music_audio_path: str | Path,
    output_audio_path: str | Path,
    ducking_attenuation_db: float = -14.0,
) -> List[str]:
    """Build FFmpeg command to mix narration and music with ducking for a Radio Cut."""
    ffmpeg_bin = get_config().ffmpeg.ffmpeg_path
    filter_graph = (
        f"[1:a]volume=0.12[bgm];"
        f"[bgm][0:a]sidechaincompress=threshold=0.125:ratio=4:attack=20:release=300[ducked];"
        f"[0:a][ducked]amix=inputs=2:duration=longest:dropout_transition=2,"
        f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
    )
    codec = "pcm_s16le" if str(output_audio_path).endswith(".wav") else "libmp3lame"
    return [
        ffmpeg_bin,
        "-y",
        "-i", str(narration_audio_path),
        "-i", str(music_audio_path),
        "-filter_complex", filter_graph,
        "-map", "[aout]",
        "-c:a", codec,
        str(output_audio_path),
    ]


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


def build_scaled_concat_command(
    video_paths: List[str | Path],
    output_path: str | Path,
    aspect_ratio: str = "16:9",
    fps: int = 24,
) -> List[str]:
    """Build FFmpeg command that normalizes every clip to the target aspect/fps and concatenates them.

    Re-encodes (concat filter) so clips with differing sizes, e.g. shots and the end card, can be joined.
    """
    ffmpeg_bin = get_config().ffmpeg.ffmpeg_path
    aspect_filter = build_aspect_ratio_filter(aspect_ratio)
    cmd: List[str] = [ffmpeg_bin, "-y"]
    parts = []
    for i, p in enumerate(video_paths):
        cmd.extend(["-i", str(p)])
        parts.append(f"[{i}:v]{aspect_filter},fps={fps},format=yuv420p[v{i}]")
    labels = "".join(f"[v{i}]" for i in range(len(video_paths)))
    graph = ";".join(parts) + f";{labels}concat=n={len(video_paths)}:v=1:a=0[vcat]"
    cmd.extend([
        "-filter_complex", graph,
        "-map", "[vcat]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ])
    return cmd


def pick_motion(camera_movement: str) -> str:
    """Map a storyboard camera_movement description to a Ken Burns motion name."""
    c = (camera_movement or "").lower()
    if "orbit" in c:
        return "orbit"
    if "zoom out" in c or "pull" in c:
        return "zoom_out"
    if "pan right" in c or "track right" in c:
        return "pan_right"
    if "pan left" in c or "track left" in c:
        return "pan_left"
    if "up" in c and ("tilt" in c or "pedestal" in c or "crane" in c):
        return "tilt_up"
    if "down" in c or "tilt" in c:
        return "tilt_down" if "down" in c else "tilt_up"
    if "static" in c:
        return "gentle"
    if "dolly" in c or "push" in c or "zoom" in c:
        return "zoom_in"
    return "zoom_in"


def build_kenburns_command(
    image_path: str | Path,
    output_path: str | Path,
    duration: float = 7.5,
    motion: str = "zoom_in",
    fps: int = 24,
    size: tuple[int, int] = (1280, 720),
) -> List[str]:
    """Build FFmpeg command that animates a still image with a smooth camera move (Ken Burns)."""
    ffmpeg_bin = get_config().ffmpeg.ffmpeg_path
    n = max(1, int(round(duration * fps)))
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    moves = {
        "zoom_in": (f"1+0.25*on/{n}", cx, cy),
        "gentle": (f"1+0.10*on/{n}", cx, cy),
        "zoom_out": (f"1.25-0.25*on/{n}", cx, cy),
        "pan_right": ("1.20", f"(iw-iw/zoom)*on/{n}", cy),
        "pan_left": ("1.20", f"(iw-iw/zoom)*(1-on/{n})", cy),
        "tilt_up": ("1.20", cx, f"(ih-ih/zoom)*(1-on/{n})"),
        "tilt_down": ("1.20", cx, f"(ih-ih/zoom)*on/{n}"),
        "orbit": (f"1.08+0.10*on/{n}", f"{cx}+iw*0.04*sin(2*PI*on/{n})", cy),
    }
    if motion not in moves:
        raise ValueError(f"Unknown motion: {motion}")
    z, x, y = moves[motion]
    w, h = size
    # Center-crop to the output aspect, upscale for sub-pixel smoothness, then animate with zoompan.
    vf = (
        f"scale={w*2.25:.0f}:{h*2.25:.0f}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={w*2.25:.0f}:{h*2.25:.0f},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={n}:s={w}x{h}:fps={fps},"
        f"format=yuv420p"
    )
    return [
        ffmpeg_bin, "-y", "-i", str(image_path),
        "-vf", vf,
        "-frames:v", str(n),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
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
        # libass PlayRes is 384x288, so FontSize scales with video height.
        size, margin = (11, 18) if aspect_ratio != "9:16" else (6, 45)
        style = f"FontName=Arial,FontSize={size},Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,Alignment=2,MarginV={margin}"
        video_filter += f",subtitles='{escaped_srt}':force_style='{style}'"

    audio_filter = build_audio_ducking_filter(
        narration_input_index=1,
        music_input_index=2,
        ducking_attenuation_db=ducking_attenuation_db,
    )
    # Pad audio with silence so -shortest ends at the video (keeps the silent end card).
    audio_filter = audio_filter.replace("[aout]", ",apad[aout]")

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
    try:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or "").strip().splitlines()[-8:]
        raise RuntimeError(
            f"FFmpeg failed (exit {exc.returncode}) running {Path(args[-1]).name}:\n" + "\n".join(tail)
        ) from exc


def synthesize_fallback_ducked_mix(
    narration_path: Path,
    music_path: Path,
    output_path: Path,
    ducking_factor: float = 0.20,
) -> Path:
    """Synthesize a sidechain ducked audio mix purely in Python when FFmpeg is not installed.

    Reads narration and music WAV files, detects speech energy, ducks music amplitude by ducking_factor,
    sums the channels, and writes a normalized 44.1kHz stereo WAV file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Read narration
    with wave.open(str(narration_path), "rb") as n_wf:
        n_sr = n_wf.getframerate()
        n_ch = n_wf.getnchannels()
        n_frames = n_wf.readframes(n_wf.getnframes())

    # Read music
    with wave.open(str(music_path), "rb") as m_wf:
        m_sr = m_wf.getframerate()
        m_ch = m_wf.getnchannels()
        m_frames = m_wf.readframes(m_wf.getnframes())

    # Standardize to 44.1kHz
    out_sr = 44100
    n_samples_count = len(n_frames) // (2 * n_ch)
    m_samples_count = len(m_frames) // (2 * m_ch)
    total_samples = max(n_samples_count, m_samples_count)

    n_ints = struct.unpack(f"<{n_samples_count * n_ch}h", n_frames)
    m_ints = struct.unpack(f"<{m_samples_count * m_ch}h", m_frames)

    out_frames = bytearray()
    smooth_duck = 1.0

    for i in range(total_samples):
        # Extract narration sample
        if i < n_samples_count:
            n_val = n_ints[i * n_ch] / 32768.0
        else:
            n_val = 0.0

        # Extract music sample
        if i < m_samples_count:
            m_val = m_ints[i * m_ch] / 32768.0
        else:
            m_val = 0.0

        # Sidechain envelope detection
        is_speaking = abs(n_val) > 0.04
        target_gain = ducking_factor if is_speaking else 0.50
        smooth_duck += (target_gain - smooth_duck) * 0.01

        # Ducked mix
        mixed = n_val * 0.90 + (m_val * smooth_duck)
        clamped = max(-32768, min(32767, int(mixed * 32767.0)))
        out_frames.extend(struct.pack("<hh", clamped, clamped))

    with wave.open(str(output_path), "wb") as out_wf:
        out_wf.setnchannels(2)
        out_wf.setsampwidth(2)
        out_wf.setframerate(out_sr)
        out_wf.writeframes(out_frames)

    return output_path
