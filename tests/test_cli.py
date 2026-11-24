"""Tests for pipeline CLI commands and execution flow."""

import pytest
from pipeline.cli import build_parser


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

