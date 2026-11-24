"""Tests for caching logic and reproducibility."""

from pathlib import Path
import tempfile
import pytest
from pipeline.cache import CacheManager


@pytest.fixture
def temp_cache():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield CacheManager(cache_dir=Path(tmp_dir))


def test_keyframe_key_deterministic(temp_cache):
    key1 = temp_cache.keyframe_key(
        prompt="Grandmother smiling",
        ref_image_path=None,
        model_id="flux-schnell",
        generation_settings={"steps": 4},
        seed=42,
    )
    key2 = temp_cache.keyframe_key(
        prompt="Grandmother smiling",
        ref_image_path=None,
        model_id="flux-schnell",
        generation_settings={"steps": 4},
        seed=42,
    )
    assert key1 == key2


def test_keyframe_key_changes_with_seed(temp_cache):
    key1 = temp_cache.keyframe_key(
        prompt="Grandmother smiling",
        ref_image_path=None,
        model_id="flux-schnell",
        generation_settings={"steps": 4},
        seed=42,
    )
    key2 = temp_cache.keyframe_key(
        prompt="Grandmother smiling",
        ref_image_path=None,
        model_id="flux-schnell",
        generation_settings={"steps": 4},
        seed=999,
    )
    assert key1 != key2


def test_cache_miss_when_file_not_on_disk(temp_cache, tmp_path):
    key = "sample_key_123"
    non_existent = tmp_path / "missing.png"
    temp_cache.put("keyframes", key, non_existent)
    # File does not exist on disk, should be a miss
    assert temp_cache.is_cached("keyframes", key, non_existent) is False


def test_cache_hit_when_file_exists(temp_cache, tmp_path):
    key = "sample_key_456"
    existing_file = tmp_path / "exists.png"
    existing_file.write_bytes(b"dummy image data")
    temp_cache.put("keyframes", key, existing_file)
    assert temp_cache.is_cached("keyframes", key, existing_file) is True


def test_cache_invalidation(temp_cache, tmp_path):
    key = "sample_key_789"
    file = tmp_path / "shot_01.mp4"
    file.write_bytes(b"dummy video data")
    temp_cache.put("shots", key, file)
    assert temp_cache.is_cached("shots", key, file) is True

    # Invalidate shots stage
    temp_cache.invalidate(stage="shots")
    assert temp_cache.is_cached("shots", key, file) is False


def test_granular_shot_isolation(temp_cache):
    """Changing one shot does not alter other shots' cache keys."""
    shot1_v1 = temp_cache.keyframe_key("Prompt 1", None, "flux", {}, seed=1)
    shot2 = temp_cache.keyframe_key("Prompt 2", None, "flux", {}, seed=2)

    shot1_v2 = temp_cache.keyframe_key("Prompt 1 Modified", None, "flux", {}, seed=1)

    assert shot1_v1 != shot1_v2
    # Shot 2 key remains unchanged
    assert shot2 == temp_cache.keyframe_key("Prompt 2", None, "flux", {}, seed=2)

