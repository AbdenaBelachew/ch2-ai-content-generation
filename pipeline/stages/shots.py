"""Stage 3: Video Shot Generation using Wan 2.2 TI2V-5B on Kaggle GPUs."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.cache import get_cache
from pipeline.config import get_config
from pipeline.logger import get_logger
from pipeline.providers.kaggle import KaggleProvider
from pipeline.validator import load_json


class ShotsStage:
    def __init__(
        self,
        kaggle_provider: Optional[KaggleProvider] = None,
        mock_if_unconfigured: bool = False,
    ):
        self.config = get_config()
        self.cache = get_cache()
        self.logger = get_logger()
        self.provider = kaggle_provider or KaggleProvider()
        self.mock_if_unconfigured = mock_if_unconfigured
        self.output_dir = self.config.output_dir / "shots"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.keyframes_dir = self.config.output_dir / "keyframes"

    def run(
        self,
        storyboard_path: Optional[str | Path] = None,
        force_regenerate: bool = False,
        shot_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate Wan 2.2 TI2V-5B video clips, using cached outputs where unchanged."""
        path = Path(storyboard_path or self.config.storyboard_path)
        storyboard = load_json(path)
        shots = storyboard.get("shots", [])

        results: Dict[str, Path] = {}
        shots_to_generate: List[Dict[str, Any]] = []

        model_id = "Wan2.2-TI2V-5B"

        for shot in shots:
            shot_id = shot["shot_id"]
            if shot_ids and shot_id not in shot_ids:
                continue

            motion_prompt = shot.get("motion_prompt", "")
            gen_settings = shot.get("generation_settings", {})
            kf_path = self.keyframes_dir / f"{shot_id}.png"
            out_file = self.output_dir / f"{shot_id}.mp4"

            cache_key = self.cache.shot_key(
                keyframe_path=kf_path,
                motion_prompt=motion_prompt,
                model_id=model_id,
                generation_settings=gen_settings,
            )

            if not force_regenerate and self.cache.is_cached("shots", cache_key, out_file):
                self.logger.log(
                    stage="shots",
                    provider="kaggle",
                    model=model_id,
                    status="CACHED",
                    shot_id=shot_id,
                    prompt_hash=cache_key,
                    output_paths=[str(out_file)],
                )
                results[shot_id] = out_file
                continue

            shots_to_generate.append(shot)

        # Always prepare Wan batch manifest for Kaggle execution
        batch_manifest_path = self.config.base_dir / "kaggle" / "wan_batch.json"
        manifest = self.provider.prepare_wan_batch(
            shots_data=shots_to_generate if shots_to_generate else shots,
            keyframes_dir=self.keyframes_dir,
            batch_output_file=batch_manifest_path,
        )

        if not shots_to_generate:
            return {"status": "ALL_CACHED", "shots": results}

        # If mock mode enabled (e.g. during test runs or unconfigured environments)
        if self.mock_if_unconfigured or not self.provider.config.is_configured:
            if self.mock_if_unconfigured:
                for shot in shots_to_generate:
                    shot_id = shot["shot_id"]
                    out_file = self.output_dir / f"{shot_id}.mp4"
                    self.provider.generate_mock_video(out_file, duration=shot.get("duration", 7.5))
                    cache_key = self.cache.shot_key(
                        keyframe_path=self.keyframes_dir / f"{shot_id}.png",
                        motion_prompt=shot.get("motion_prompt", ""),
                        model_id=model_id,
                        generation_settings=shot.get("generation_settings", {}),
                    )
                    self.cache.put(
                        stage="shots",
                        cache_key=cache_key,
                        output_path=out_file,
                        metadata={"shot_id": shot_id, "mock": True},
                    )
                    self.logger.log(
                        stage="shots",
                        provider="mock",
                        model=model_id,
                        status="SUCCESS",
                        shot_id=shot_id,
                        output_paths=[str(out_file)],
                    )
                    results[shot_id] = out_file
                return {"status": "COMPLETED_MOCK", "shots": results}

            # Return instructions for manual Kaggle execution
            return {
                "status": "REQUIRES_KAGGLE_GPU",
                "message": (
                    f"{len(shots_to_generate)} shots need generation. "
                    f"Kaggle batch manifest prepared at: {batch_manifest_path}. "
                    "Run Kaggle notebook 'kaggle/wan2_ti2v_runner.py' and place output MP4s in outputs/shots/."
                ),
                "batch_manifest": str(batch_manifest_path),
                "pending_shots": [s["shot_id"] for s in shots_to_generate],
                "cached_shots": results,
            }

        return {"status": "TRIGGERED", "shots": results}

