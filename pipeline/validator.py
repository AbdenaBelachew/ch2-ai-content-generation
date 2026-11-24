"""Storyboard validation module.

Validates storyboard.json against JSON Schema and business logic constraints:
- Duration bounds (60-90s).
- Unique shot IDs.
- Valid character references.
- Missing required fields.
- Amharic script presence and English translation.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import jsonschema
from pipeline.config import get_config


class StoryboardValidationError(Exception):
    """Raised when storyboard fails validation."""
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def load_json(path: str | Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_storyboard_dict(
    storyboard: Dict[str, Any],
    schema: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    """Validate a storyboard dictionary against schema and business constraints."""
    errors: List[str] = []

    # 1. JSON Schema validation
    if schema is None:
        schema_path = get_config().schema_path
        if schema_path.is_file():
            schema = load_json(schema_path)

    if schema:
        validator = jsonschema.Draft202012Validator(schema)
        schema_errors = sorted(validator.iter_errors(storyboard), key=lambda e: e.path)
        for err in schema_errors:
            field = ".".join(str(p) for p in err.path) if err.path else "root"
            errors.append(f"Schema error at '{field}': {err.message}")

    # 2. Duplicate Shot IDs check
    shots = storyboard.get("shots", [])
    seen_shot_ids = set()
    for idx, shot in enumerate(shots):
        shot_id = shot.get("shot_id")
        if not shot_id:
            errors.append(f"Shot at index {idx} is missing 'shot_id'")
        elif shot_id in seen_shot_ids:
            errors.append(f"Duplicate shot_id found: '{shot_id}'")
        else:
            seen_shot_ids.add(shot_id)

    # 3. Shot count validation
    if len(shots) < 8 or len(shots) > 12:
        errors.append(f"Storyboard must contain between 8 and 12 shots; found {len(shots)}")

    # 4. Duration validation
    total_duration = sum(float(shot.get("duration", 0)) for shot in shots)
    if total_duration < 60.0 or total_duration > 90.0:
        errors.append(
            f"Total shot duration ({total_duration:.1f}s) is outside the required 60–90 second range"
        )

    target_total = storyboard.get("project_metadata", {}).get("target_total_duration")
    if target_total is not None:
        target_total = float(target_total)
        if abs(total_duration - target_total) > 2.0:
            errors.append(
                f"Sum of shot durations ({total_duration:.1f}s) diverges from target_total_duration ({target_total:.1f}s)"
            )

    # 5. Character references integrity
    char_refs = storyboard.get("character_references", [])
    valid_char_ids = {c.get("character_id") for c in char_refs if c.get("character_id")}
    for shot in shots:
        shot_id = shot.get("shot_id", "unknown")
        for cid in shot.get("character_reference_ids", []):
            if cid not in valid_char_ids:
                errors.append(
                    f"Shot '{shot_id}' references undefined character_id: '{cid}'"
                )

    # 6. Narration & translation completeness
    for shot in shots:
        shot_id = shot.get("shot_id", "unknown")
        narration_am = shot.get("narration_amharic", "").strip()
        trans_en = shot.get("english_translation", "").strip()
        if not narration_am:
            errors.append(f"Shot '{shot_id}' is missing required 'narration_amharic'")
        if not trans_en:
            errors.append(f"Shot '{shot_id}' is missing required 'english_translation'")

    return len(errors) == 0, errors


def validate_storyboard_file(file_path: Optional[str | Path] = None) -> Tuple[bool, List[str]]:
    """Validate storyboard file from disk."""
    if file_path is None:
        file_path = get_config().storyboard_path
    path = Path(file_path)
    if not path.is_file():
        return False, [f"Storyboard file not found at {path}"]
    try:
        data = load_json(path)
    except Exception as exc:
        return False, [f"Failed to parse storyboard JSON at {path}: {exc}"]
    return validate_storyboard_dict(data)
