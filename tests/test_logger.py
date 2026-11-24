"""Tests for audit run logger."""

import json
from pathlib import Path
import tempfile
import pytest
from pipeline.logger import PipelineLogger, RunRecord


@pytest.fixture
def temp_logger():
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "runs.jsonl"
        yield PipelineLogger(log_path=log_file), log_file


def test_log_run_appends_record(temp_logger):
    logger, log_file = temp_logger

    rec = logger.log(
        stage="keyframes",
        provider="cloudflare",
        model="@cf/black-forest-labs/flux-1-schnell",
        status="SUCCESS",
        shot_id="shot_01",
        prompt="Golden sunrise over Ethiopian highlands",
        generation_parameters={"steps": 4},
        seed=42,
        execution_duration_sec=2.15,
    )

    assert log_file.is_file()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["stage"] == "keyframes"
    assert entry["provider"] == "cloudflare"
    assert entry["model"] == "@cf/black-forest-labs/flux-1-schnell"
    assert entry["status"] == "SUCCESS"
    assert entry["shot_id"] == "shot_01"
    assert entry["seed"] == 42
    assert entry["execution_duration_sec"] == 2.15
    assert "timestamp" in entry
    assert "cost_usd" not in entry  # Not invented


def test_log_multiple_runs(temp_logger):
    logger, log_file = temp_logger
    logger.log(stage="narration", provider="gemini", model="tts", status="SUCCESS", shot_id="shot_01")
    logger.log(stage="narration", provider="gemini", model="tts", status="CACHED", shot_id="shot_02")

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    data1 = json.loads(lines[0])
    data2 = json.loads(lines[1])
    assert data1["status"] == "SUCCESS"
    assert data2["status"] == "CACHED"

