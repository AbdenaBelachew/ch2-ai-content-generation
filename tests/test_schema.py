"""Tests for Storyboard JSON Schema compliance."""

import copy
import json
from pathlib import Path
import pytest
import jsonschema


@pytest.fixture
def schema_and_storyboard():
    schema_path = Path("schema/storyboard.schema.json")
    sb_path = Path("storyboard.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    with open(sb_path, "r", encoding="utf-8") as f:
        storyboard = json.load(f)
    return schema, storyboard


def test_storyboard_matches_schema(schema_and_storyboard):
    """The default initial storyboard must strictly validate against the schema."""
    schema, storyboard = schema_and_storyboard
    jsonschema.validate(instance=storyboard, schema=schema)


def test_schema_rejects_missing_metadata(schema_and_storyboard):
    """Schema must reject a storyboard without project_metadata."""
    schema, storyboard = schema_and_storyboard
    bad_sb = copy.deepcopy(storyboard)
    del bad_sb["project_metadata"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad_sb, schema=schema)


def test_schema_rejects_too_few_shots(schema_and_storyboard):
    """Schema must reject storyboards with fewer than 8 shots."""
    schema, storyboard = schema_and_storyboard
    bad_sb = copy.deepcopy(storyboard)
    bad_sb["shots"] = bad_sb["shots"][:5]  # Only 5 shots
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad_sb, schema=schema)


def test_schema_rejects_too_many_shots(schema_and_storyboard):
    """Schema must reject storyboards with more than 12 shots."""
    schema, storyboard = schema_and_storyboard
    bad_sb = copy.deepcopy(storyboard)
    # Duplicate shots to exceed 12
    bad_sb["shots"] = bad_sb["shots"] + bad_sb["shots"][:5]  # 15 shots
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad_sb, schema=schema)


def test_schema_rejects_invalid_aspect_ratio(schema_and_storyboard):
    """Schema must reject invalid aspect ratios."""
    schema, storyboard = schema_and_storyboard
    bad_sb = copy.deepcopy(storyboard)
    bad_sb["output_aspect_ratios"] = ["4:3"]  # Not in allowed enum
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad_sb, schema=schema)

