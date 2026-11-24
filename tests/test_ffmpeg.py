"""Tests for FFmpeg command construction and assembly utilities."""

from pathlib import Path
import pytest
from pipeline.utils.ffmpeg import (
    build_aspect_ratio_filter,
    build_audio_ducking_filter,
    build_end_card_command,
    build_final_assembly_command,
    format_srt_timestamp,
    generate_srt,
)


def test_format_srt_timestamp():
    assert format_srt_timestamp(0.0) == "00:00:00,000"
    assert format_srt_timestamp(7.5) == "00:00:07,500"
    assert format_srt_timestamp(75.25) == "00:01:15,250"


def test_generate_srt(tmp_path):
    shots = [
        {"duration": 7.5, "english_translation": "First sunrise of morning."},
        {"duration": 7.5, "english_translation": "Grandmother prepares coffee."},
    ]
    srt_file = tmp_path / "test.srt"
    generate_srt(shots, srt_file)

    assert srt_file.exists()
    content = srt_file.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:07,500" in content
    assert "First sunrise of morning." in content
    assert "00:00:07,500 --> 00:00:15,000" in content
    assert "Grandmother prepares coffee." in content


def test_build_audio_ducking_filter():
    filter_graph = build_audio_ducking_filter(narration_input_index=1, music_input_index=2)
    assert "sidechaincompress" in filter_graph
    assert "loudnorm" in filter_graph
    assert "amix" in filter_graph


def test_build_aspect_ratio_filter():
    filter_16x9 = build_aspect_ratio_filter("16:9")
    assert "1920:1080" in filter_16x9
    assert "force_original_aspect_ratio=increase" in filter_16x9

    filter_9x16 = build_aspect_ratio_filter("9:16")
    assert "1080:1920" in filter_9x16
    assert "crop=1080:1920" in filter_9x16

    with pytest.raises(ValueError):
        build_aspect_ratio_filter("unsupported_ratio")


def test_build_end_card_command():
    cmd = build_end_card_command(
        title="AI Heritage Short",
        disclosure_text="This film was generated with AI.",
        duration=4.0,
        output_video_path="outputs/assembly/end_card_16x9.mp4",
        aspect_ratio="16:9",
    )
    assert any("color=c=black:s=1920x1080:d=4.0" in arg for arg in cmd)
    assert any("drawtext=" in arg for arg in cmd)
    assert "outputs/assembly/end_card_16x9.mp4" in cmd[-1]


def test_build_final_assembly_command():
    cmd = build_final_assembly_command(
        video_input_path="outputs/shots/shot_01.mp4",
        narration_audio_path="outputs/narration/full_narration.wav",
        music_audio_path="outputs/music/soundtrack.wav",
        output_path="outputs/exports/film_16x9.mp4",
        aspect_ratio="16:9",
        ducking_attenuation_db=-14.0,
    )
    assert "-filter_complex" in cmd
    assert "-shortest" in cmd
    assert "outputs/exports/film_16x9.mp4" in cmd[-1]

