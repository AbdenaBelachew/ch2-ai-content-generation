"""Stage 4: Original Soundtrack Generation using ACE-Step 1.5 on Kaggle GPUs."""

from pathlib import Path
from typing import Any, Dict, Optional
from pipeline.cache import get_cache
from pipeline.config import get_config
from pipeline.logger import get_logger
from pipeline.providers.kaggle import KaggleProvider
from pipeline.validator import load_json


class MusicStage:
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
        self.output_dir = self.config.output_dir / "music"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        storyboard_path: Optional[str | Path] = None,
        force_regenerate: bool = False,
    ) -> Dict[str, Any]:
        """Generate original soundtrack or prepare Kaggle execution batch."""
        path = Path(storyboard_path or self.config.storyboard_path)
        storyboard = load_json(path)
        music_settings = storyboard.get("music_settings", {})

        model_id = "ACE-Step-1.5"
        music_prompt = music_settings.get("prompt", "")
        out_file = self.output_dir / "soundtrack.wav"

        cache_key = self.cache.music_key(
            music_prompt=music_prompt,
            generation_settings=music_settings,
            model_id=model_id,
        )

        if not force_regenerate and self.cache.is_cached("music", cache_key, out_file):
            self.logger.log(
                stage="music",
                provider="kaggle",
                model=model_id,
                status="CACHED",
                prompt_hash=cache_key,
                output_paths=[str(out_file)],
            )
            return {"status": "CACHED", "soundtrack_path": out_file}

        # Prepare ACE-Step Kaggle batch payload
        batch_manifest_path = self.config.base_dir / "kaggle" / "acestep_batch.json"
        manifest = self.provider.prepare_acestep_batch(
            music_settings=music_settings,
            batch_output_file=batch_manifest_path,
        )

        if self.mock_if_unconfigured or not self.provider.config.is_configured:
            if self.mock_if_unconfigured:
                generated_path = self.provider.generate_mock_music(
                    out_file, duration=float(music_settings.get("target_duration", 78.0))
                )
                self.cache.put(
                    stage="music",
                    cache_key=cache_key,
                    output_path=generated_path,
                    metadata={"mock": True, "prompt": music_prompt[:80]},
                )
                self.logger.log(
                    stage="music",
                    provider="mock",
                    model=model_id,
                    status="SUCCESS",
                    output_paths=[str(generated_path)],
                )
                return {"status": "COMPLETED_MOCK", "soundtrack_path": generated_path}

            return {
                "status": "REQUIRES_KAGGLE_GPU",
                "message": (
                    f"ACE-Step music manifest generated at: {batch_manifest_path}. "
                    "Run Kaggle notebook 'kaggle/ace_step_runner.py' and place output at outputs/music/soundtrack.wav."
                ),
                "batch_manifest": str(batch_manifest_path),
            }

        return {"status": "TRIGGERED", "batch_manifest": str(batch_manifest_path)}

