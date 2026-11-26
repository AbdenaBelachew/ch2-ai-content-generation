"""Placeholder rejection, planned-duration fitting, and Kaggle runner helpers (no GPU needed)."""

import importlib.util
import sys
from pathlib import Path

from pipeline.utils.ffmpeg import build_scaled_concat_command
from pipeline.utils.media import audio_problem, video_problem

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "kaggle" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_placeholder_video_is_rejected(tmp_path):
    fake = tmp_path / "shot_01.mp4"
    fake.write_bytes(b"\x00\x00\x00 ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free")
    assert "placeholder" in video_problem(fake)
    assert video_problem(tmp_path / "missing.mp4") == "file does not exist"


def test_silent_tiny_wav_is_rejected(tmp_path):
    import wave
    p = tmp_path / "s.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\x00\x00" * 10)
    assert audio_problem(p) is not None


def test_concat_pads_and_trims_without_stretching():
    cmd = build_scaled_concat_command(["a.mp4", "b.mp4"], "o.mp4", "16:9", durations=[7.5, None])
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "tpad=stop_mode=clone:stop_duration=7.500,trim=duration=7.500" in graph
    assert graph.count("tpad") == 1  # clip with no planned duration is untouched
    assert "setpts=PTS*" not in graph  # never time-stretch


def test_wan_frame_count_is_4k_plus_1_and_capped():
    wan = _load("wan2_ti2v_runner")
    assert wan.frames_for(7.5, 24, 121) == 121
    assert wan.frames_for(2.0, 24, 121) == 45
    assert (wan.frames_for(3.3, 24, 500) - 1) % 4 == 0


def test_wan_size_keeps_aspect_and_snaps_to_multiple():
    wan = _load("wan2_ti2v_runner")
    w, h = wan.fit_size(1024, 1792, 480 * 832, 32)
    assert w % 32 == 0 and h % 32 == 0 and h > w
    assert w * h <= 480 * 832


def test_acestep_caption_respects_limit():
    ace = _load("ace_step_runner")
    cap = ace.build_caption({"prompt": "x" * 600, "instrumentation": ["Krar"], "mood": "warm"})
    assert len(cap) <= 512
