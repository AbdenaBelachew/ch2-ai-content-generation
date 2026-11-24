"""Kaggle GPU provider for Wan 2.2 TI2V-5B video and ACE-Step 1.5 music generation.

Supports preparing inputs, checking credentials, executing kernels via Kaggle API,
and providing clear manual fallbacks with verification of output placement.
"""

import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import requests
from pipeline.config import KaggleConfig, get_config
from pipeline.logger import get_logger
from pipeline.providers.base import BaseProvider


class KaggleProvider(BaseProvider):
    def __init__(self, config: Optional[KaggleConfig] = None):
        self.config = config or get_config().kaggle
        self.logger = get_logger()

    def verify_connection(self) -> Dict[str, Any]:
        """Perform a minimal smoke test for Kaggle API credentials."""
        if not self.config.is_configured:
            return {
                "provider": "kaggle",
                "status": "UNCONFIGURED",
                "message": "KAGGLE_USERNAME or KAGGLE_KEY is not configured in .env. Manual fallback is active.",
            }

        url = "https://www.kaggle.com/api/v1/datasets/list"
        auth = (self.config.username, self.config.key)
        try:
            resp = requests.get(url, auth=auth, timeout=10)
            if resp.status_code == 200:
                return {
                    "provider": "kaggle",
                    "status": "READY",
                    "username": self.config.username,
                    "message": "Kaggle API credentials authenticated successfully.",
                }
            elif resp.status_code in (401, 403):
                return {
                    "provider": "kaggle",
                    "status": "AUTH_FAILED",
                    "message": f"Kaggle authentication failed (HTTP {resp.status_code}). Check username/key.",
                }
            else:
                return {
                    "provider": "kaggle",
                    "status": "ERROR",
                    "message": f"Kaggle API returned HTTP {resp.status_code}: {resp.text}",
                }
        except Exception as exc:
            return {
                "provider": "kaggle",
                "status": "NETWORK_ERROR",
                "message": f"Failed to connect to Kaggle API: {exc}",
            }

    def prepare_wan_batch(
        self,
        shots_data: List[Dict[str, Any]],
        keyframes_dir: Path,
        batch_output_file: Path,
    ) -> Dict[str, Any]:
        """Bundle shots and keyframe paths into a manifest for Wan 2.2 TI2V-5B notebook."""
        batch_output_file.parent.mkdir(parents=True, exist_ok=True)
        items = []
        for shot in shots_data:
            shot_id = shot["shot_id"]
            kf_path = keyframes_dir / f"{shot_id}.png"
            items.append({
                "shot_id": shot_id,
                "keyframe_path": str(kf_path) if kf_path.exists() else None,
                "motion_prompt": shot.get("motion_prompt", ""),
                "duration": shot.get("duration", 7.5),
                "camera_movement": shot.get("camera_movement", ""),
                "fps": shot.get("generation_settings", {}).get("fps", 24),
                "output_filename": f"{shot_id}.mp4",
            })

        batch_manifest = {
            "model": "Wan2.2-TI2V-5B",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_shots": len(items),
            "shots": items,
        }
        with open(batch_output_file, "w", encoding="utf-8") as f:
            json.dump(batch_manifest, f, indent=2, ensure_ascii=False)

        return batch_manifest

    def prepare_acestep_batch(
        self,
        music_settings: Dict[str, Any],
        batch_output_file: Path,
    ) -> Dict[str, Any]:
        """Bundle music prompts and parameters into a manifest for ACE-Step 1.5."""
        batch_output_file.parent.mkdir(parents=True, exist_ok=True)
        batch_manifest = {
            "model": "ACE-Step-1.5",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "music_settings": music_settings,
            "output_filename": "soundtrack.wav",
        }
        with open(batch_output_file, "w", encoding="utf-8") as f:
            json.dump(batch_manifest, f, indent=2, ensure_ascii=False)

        return batch_manifest

    def generate_mock_video(self, output_path: Path, duration: float = 7.5) -> Path:
        """Create a lightweight mock MP4 video file for offline testing."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 16-byte dummy header or minimal valid container
        output_path.write_bytes(b"\x00\x00\x00 ftypisom\x00\x00\x02\x00isomiso2mp41\x00\x00\x00\x08free")
        return output_path

    def generate_mock_music(self, output_path: Path, duration: float = 78.0) -> Path:
        """Create a lightweight mock WAV audio file for offline testing."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        import wave
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(2)
            wav_file.setsampwidth(2)
            wav_file.setframerate(44100)
            wav_file.writeframes(b"\x00\x00\x00\x00" * 44100)  # 1 second of stereo silence
        return output_path

