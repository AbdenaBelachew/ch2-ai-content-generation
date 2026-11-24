"""Stage 5: Amharic Narration Generation using Gemini TTS."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.cache import get_cache
from pipeline.config import get_config
from pipeline.logger import get_logger
from pipeline.providers.gemini import GeminiProvider
from pipeline.validator import load_json


class NarrationStage:
    def __init__(
        self,
        gemini_provider: Optional[GeminiProvider] = None,
        mock_if_unconfigured: bool = False,
    ):
        self.config = get_config()
        self.cache = get_cache()
        self.logger = get_logger()
        self.provider = gemini_provider or GeminiProvider()
        self.mock_if_unconfigured = mock_if_unconfigured
        self.output_dir = self.config.output_dir / "narration"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        storyboard_path: Optional[str | Path] = None,
        force_regenerate: bool = False,
        shot_ids: Optional[List[str]] = None,
    ) -> Dict[str, Path]:
        """Generate Amharic speech audio files for storyboard shots."""
        path = Path(storyboard_path or self.config.storyboard_path)
        storyboard = load_json(path)
        shots = storyboard.get("shots", [])

        voice_config = {
            "language": storyboard.get("narration_language", "Amharic"),
            "voice_name": "am-ET-Standard-A",
            "gender": "FEMALE",
        }
        model_id = self.provider.config.tts_model
        results: Dict[str, Path] = {}

        for shot in shots:
            shot_id = shot["shot_id"]
            if shot_ids and shot_id not in shot_ids:
                continue

            amharic_text = shot.get("narration_amharic", "")
            out_file = self.output_dir / f"{shot_id}.wav"

            cache_key = self.cache.narration_key(
                amharic_text=amharic_text,
                voice_config=voice_config,
                model_id=model_id,
            )

            if not force_regenerate and self.cache.is_cached("narration", cache_key, out_file):
                self.logger.log(
                    stage="narration",
                    provider="gemini",
                    model=model_id,
                    status="CACHED",
                    shot_id=shot_id,
                    prompt_hash=cache_key,
                    output_paths=[str(out_file)],
                )
                results[shot_id] = out_file
                continue

            # Generate via provider
            generated_path = self.provider.generate_amharic_tts(
                amharic_text=amharic_text,
                output_audio_path=out_file,
                voice_name=voice_config["voice_name"],
                mock_if_unconfigured=self.mock_if_unconfigured,
            )

            self.cache.put(
                stage="narration",
                cache_key=cache_key,
                output_path=generated_path,
                metadata={"shot_id": shot_id, "text_preview": amharic_text[:40]},
            )
            results[shot_id] = generated_path

        # Create combined full narration audio track
        self._combine_narration_audio(shots, results, self.output_dir / "full_narration.wav")

        return results

    def _combine_narration_audio(
        self,
        shots: List[Dict[str, Any]],
        shot_audio_map: Dict[str, Path],
        full_audio_path: Path,
    ) -> None:
        """Combine individual shot narrations into a continuous full-track audio file."""
        import wave
        
        frames = []
        sample_rate = 24000
        n_channels = 1
        samp_width = 2

        for shot in shots:
            shot_id = shot["shot_id"]
            audio_path = shot_audio_map.get(shot_id)
            if audio_path and audio_path.is_file():
                try:
                    with wave.open(str(audio_path), "rb") as wf:
                        sample_rate = wf.getframerate()
                        n_channels = wf.getnchannels()
                        samp_width = wf.getsampwidth()
                        frames.append(wf.readframes(wf.getnframes()))
                except Exception:
                    # In case of mock or non-wav format, pad with silence
                    target_samples = int(float(shot.get("duration", 7.5)) * sample_rate)
                    frames.append(b"\x00" * (target_samples * n_channels * samp_width))
            else:
                target_samples = int(float(shot.get("duration", 7.5)) * sample_rate)
                frames.append(b"\x00" * (target_samples * n_channels * samp_width))

        with wave.open(str(full_audio_path), "wb") as out_wf:
            out_wf.setnchannels(n_channels)
            out_wf.setsampwidth(samp_width)
            out_wf.setframerate(sample_rate)
            for f in frames:
                out_wf.writeframes(f)

