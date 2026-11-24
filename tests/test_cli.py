"""Tests for pipeline CLI commands and execution flow."""

from pathlib import Path
import pytest
from pipeline.cli import build_parser
from pipeline.providers.gemini import analyze_amharic_script
from pipeline.stages.script import ScriptStage


def test_cli_validate_command():
    parser = build_parser()
    args = parser.parse_args(["validate"])
    exit_code = args.func(args)
    assert exit_code == 0


def test_cli_status_command():
    parser = build_parser()
    args = parser.parse_args(["status"])
    exit_code = args.func(args)
    assert exit_code == 0


def test_cli_character_sheet_command():
    parser = build_parser()
    args = parser.parse_args(["keyframes", "--character-sheet", "--mock"])
    exit_code = args.func(args)
    assert exit_code == 0
    sheet = Path("outputs/keyframes/character_sheet_char_grandmother_ayelech.png")
    assert sheet.exists()


def test_cli_radio_command():
    parser = build_parser()
    args = parser.parse_args(["radio", "--mock"])
    exit_code = args.func(args)
    assert exit_code == 0
    radio_cut = Path("outputs/assembly/radio_cut.wav")
    assert radio_cut.exists()
    assert radio_cut.stat().st_size > 0


def test_amharic_analysis_and_pacing():
    sample_text = "ፀሐይ በደጋው ኮረብታዎች ላይ ስትወጣ፣ የቀደምት አባቶቻችን ትዝታ ከነፋሱ ጋር ይነጋገራል።"
    metrics = analyze_amharic_script(sample_text)
    assert metrics["is_geez_script"] is True
    assert metrics["fidel_count"] > 10
    assert metrics["estimated_duration_sec"] > 2.0

    script_stage = ScriptStage()
    pacing_report = script_stage.analyze_pacing()
    assert len(pacing_report) == 10
    for shot in pacing_report:
        assert shot["duration"] == 7.5
        assert shot["fidel_count"] > 0
        assert shot["estimated_duration_sec"] > 0
        assert "headroom_sec" in shot


def test_cli_mock_pipeline_flow():
    parser = build_parser()

    # 1. Keyframes with mock
    args_kf = parser.parse_args(["keyframes", "--mock", "--shots", "shot_01"])
    assert args_kf.func(args_kf) == 0

    # 2. Narration with mock
    args_narr = parser.parse_args(["narration", "--mock", "--shots", "shot_01"])
    assert args_narr.func(args_narr) == 0

    # 3. Shots with mock
    args_sh = parser.parse_args(["shots", "--mock", "--shots", "shot_01"])
    assert args_sh.func(args_sh) == 0

    # 4. Music with mock
    args_mus = parser.parse_args(["music", "--mock"])
    assert args_mus.func(args_mus) == 0

    # 5. Assemble with dry-run
    args_ass = parser.parse_args(["assemble", "--dry-run"])
    assert args_ass.func(args_ass) == 0
