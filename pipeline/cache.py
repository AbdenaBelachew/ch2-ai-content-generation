"""Granular, content-addressed caching system for pipeline stages.

Ensures reproducibility and prevents redundant external API or GPU calls.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from pipeline.config import get_config
from pipeline.utils.hash import hash_data, hash_file, hash_text


class CacheManager:
    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            cache_dir = get_config().cache_dir
        self.cache_dir = Path(cache_dir)
        self.manifest_path = self.cache_dir / "manifest.json"
        self._manifest: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.is_file():
            try:
                with self.manifest_path.open("r", encoding="utf-8") as f:
                    self._manifest = json.load(f)
            except Exception:
                self._manifest = {}
        else:
            self._manifest = {}

    def _save(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("w", encoding="utf-8") as f:
            json.dump(self._manifest, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # Key Computations
    # -------------------------------------------------------------------------

    @staticmethod
    def keyframe_key(
        prompt: str,
        ref_image_path: Optional[str | Path],
        model_id: str,
        generation_settings: Dict[str, Any],
        seed: Optional[int],
    ) -> str:
        """Compute keyframe cache key using prompt, reference image hash, model, settings, seed."""
        ref_hash = hash_file(ref_image_path) if ref_image_path else ""
        payload = {
            "type": "keyframe",
            "prompt": prompt.strip(),
            "ref_image_hash": ref_hash,
            "model_id": model_id.strip(),
            "generation_settings": generation_settings,
            "seed": seed,
        }
        return hash_data(payload)

    @staticmethod
    def shot_key(
        keyframe_path: str | Path,
        motion_prompt: str,
        model_id: str,
        generation_settings: Dict[str, Any],
    ) -> str:
        """Compute video shot cache key using keyframe image hash, motion prompt, model, settings."""
        kf_hash = hash_file(keyframe_path)
        payload = {
            "type": "shot_video",
            "keyframe_hash": kf_hash,
            "motion_prompt": motion_prompt.strip(),
            "model_id": model_id.strip(),
            "generation_settings": generation_settings,
        }
        return hash_data(payload)

    @staticmethod
    def narration_key(
        amharic_text: str,
        voice_config: Dict[str, Any],
        model_id: str,
    ) -> str:
        """Compute narration cache key using Amharic text, voice configuration, model ID."""
        payload = {
            "type": "narration",
            "amharic_text": amharic_text.strip(),
            "voice_config": voice_config,
            "model_id": model_id.strip(),
        }
        return hash_data(payload)

    @staticmethod
    def music_key(
        music_prompt: str,
        generation_settings: Dict[str, Any],
        model_id: str = "ACE-Step-1.5",
    ) -> str:
        """Compute music cache key using music prompt, model, and generation settings."""
        payload = {
            "type": "music",
            "music_prompt": music_prompt.strip(),
            "generation_settings": generation_settings,
            "model_id": model_id.strip(),
        }
        return hash_data(payload)

    # -------------------------------------------------------------------------
    # Cache Queries & Updates
    # -------------------------------------------------------------------------

    def is_cached(self, stage: str, cache_key: str, expected_output_path: str | Path) -> bool:
        """Return True only if the entry exists in manifest and the output file exists on disk."""
        stage_entries = self._manifest.get(stage, {})
        entry = stage_entries.get(cache_key)
        if not entry:
            return False
        
        target_path = Path(expected_output_path)
        if not target_path.exists() or target_path.stat().st_size == 0:
            return False
        
        return True

    def get_entry(self, stage: str, cache_key: str) -> Optional[Dict[str, Any]]:
        return self._manifest.get(stage, {}).get(cache_key)

    def put(
        self,
        stage: str,
        cache_key: str,
        output_path: str | Path,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store cache entry and write updated manifest."""
        if stage not in self._manifest:
            self._manifest[stage] = {}
        
        self._manifest[stage][cache_key] = {
            "output_path": str(output_path),
            "file_hash": hash_file(output_path),
            "metadata": metadata or {},
        }
        self._save()

    def invalidate(self, stage: Optional[str] = None, cache_key: Optional[str] = None) -> None:
        """Invalidate all entries, a specific stage, or a specific key."""
        if stage is None:
            self._manifest = {}
        elif cache_key is None:
            self._manifest.pop(stage, None)
        else:
            if stage in self._manifest:
                self._manifest[stage].pop(cache_key, None)
        self._save()


_CACHE: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    global _CACHE
    if _CACHE is None:
        _CACHE = CacheManager()
    return _CACHE

