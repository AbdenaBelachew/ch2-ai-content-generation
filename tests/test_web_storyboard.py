"""Tests for the web UI's storyboard builder and input validation."""

import json
import pytest
from pipeline.validator import validate_storyboard_dict
from web.server import clean_inputs
from web.storyboard_builder import StoryboardError, assemble_storyboard, generate_storyboard


def _payload(n):
    return {
        "film_title": "Test Film",
        "title_english": "Test Film",
        "story_description": "A short test story.",
        "mood": "warm",
        "character": {"name": "Aster", "description": "A kind woman.", "estimated_age": "60 years old",
                      "attire": "white dress", "facial_features": "warm eyes", "hair": "grey braids"},
        "visual_style": {"art_style": "cinematic", "lighting": "golden", "color_palette": "ochre"},
        "shots": [
            {"scene_description": f"Scene number {i}", "narration_amharic": "ሰላም ለሁሉም",
             "english_translation": f"Peace to all {i}", "image_prompt": f"A wide photo of scene {i}",
             "motion_prompt": "Slow push in", "camera_movement": "Slow pan right",
             "has_character": i % 2 == 0, "visual_purpose": "Story beat"}
            for i in range(n)
        ],
    }


INPUTS = {"idea": "A story about coffee and patience", "shots": 8, "music": "guitar", "aspects": ["16:9"]}


def test_assemble_is_schema_valid():
    sb = assemble_storyboard(INPUTS, _payload(8))
    ok, errs = validate_storyboard_dict(sb)
    assert ok, errs
    assert len(sb["shots"]) == 8
    assert sb["shots"][0]["character_reference_ids"] == ["char_aster"]
    assert sb["shots"][1]["character_reference_ids"] == []
    assert sb["output_aspect_ratios"] == ["16:9"]


def test_generate_retries_after_bad_shot_count():
    answers = [json.dumps(_payload(3)), json.dumps(_payload(8))]
    prompts = []

    def fake_llm(prompt):
        prompts.append(prompt)
        return answers.pop(0)

    sb = generate_storyboard(INPUTS, llm=fake_llm)
    assert len(sb["shots"]) == 8
    assert "REJECTED" in prompts[1]


def test_generate_gives_up_with_clear_error():
    with pytest.raises(StoryboardError):
        generate_storyboard(INPUTS, llm=lambda p: "not json", attempts=2)


def test_clean_inputs_validation():
    ok = clean_inputs({"idea": "A long enough story idea here", "shots": 10})
    assert ok["shots"] == 10 and ok["voice"] == "Kore" and ok["aspects"] == ["16:9", "9:16"]
    for bad in ({"idea": "short"}, {"idea": "A long enough story idea here", "shots": 20},
                {"idea": "A long enough story idea here", "voice": "Nope"},
                {"idea": "A long enough story idea here", "aspects": []}):
        with pytest.raises(ValueError):
            clean_inputs(bad)
