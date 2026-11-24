"""Tests for storyboard business validator logic."""

import copy
import json
from pathlib import Path
import pytest
from pipeline.validator import validate_storyboard_dict, validate_storyboard_file


@pytest.fixture
def base_storyboard():
    with open("storyboard.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_validator_succeeds_on_valid_storyboard(base_storyboard):
    valid, errors = validate_storyboard_dict(base_storyboard)
    assert valid is True
    assert len(errors) == 0


def test_validator_catches_duplicate_shot_id(base_storyboard):
    sb = copy.deepcopy(base_storyboard)
    # Make shot 2 have the same ID as shot 1
    sb["shots"][1]["shot_id"] = sb["shots"][0]["shot_id"]
    valid, errors = validate_storyboard_dict(sb)
    assert valid is False
    assert any("Duplicate shot_id found" in e for e in errors)


def test_validator_catches_missing_narration_amharic(base_storyboard):
    sb = copy.deepcopy(base_storyboard)
    sb["shots"][0]["narration_amharic"] = "   "
    valid, errors = validate_storyboard_dict(sb)
    assert valid is False
    assert any("missing required 'narration_amharic'" in e for e in errors)


def test_validator_catches_missing_english_translation(base_storyboard):
    sb = copy.deepcopy(base_storyboard)
    sb["shots"][0]["english_translation"] = ""
    valid, errors = validate_storyboard_dict(sb)
    assert valid is False
    assert any("missing required 'english_translation'" in e for e in errors)


def test_validator_catches_invalid_total_duration(base_storyboard):
    sb = copy.deepcopy(base_storyboard)
    # Set each shot to 2.0s -> total 20s (less than 60s minimum)
    for s in sb["shots"]:
        s["duration"] = 2.0
    valid, errors = validate_storyboard_dict(sb)
    assert valid is False
    assert any("outside the required 60–90 second range" in e for e in errors)


def test_validator_catches_undefined_character_id(base_storyboard):
    sb = copy.deepcopy(base_storyboard)
    sb["shots"][0]["character_reference_ids"] = ["non_existent_char"]
    valid, errors = validate_storyboard_dict(sb)
    assert valid is False
    assert any("references undefined character_id: 'non_existent_char'" in e for e in errors)


def test_validate_storyboard_file():
    valid, errors = validate_storyboard_file("storyboard.json")
    assert valid is True
    assert len(errors) == 0

