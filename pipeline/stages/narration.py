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
        failed: Dict[str, str] = {}

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

            # Generate via provider. One failing shot (e.g. API rate limit) must not lose the others.
            shot_duration = float(shot.get("duration", 7.5))
            try:
                generated_path = self.provider.generate_amharic_tts(
                    amharic_text=amharic_text,
                    output_audio_path=out_file,
                    voice_name=voice_config["voice_name"],
                    target_duration=shot_duration,
                    mock_if_unconfigured=self.mock_if_unconfigured,
                )
            except Exception as exc:
                failed[shot_id] = str(exc)[:200]
                if out_file.is_file():
                    results[shot_id] = out_file  # keep the previously generated clip
                continue

            self.cache.put(
                stage="narration",
                cache_key=cache_key,
                output_path=generated_path,
                metadata={"shot_id": shot_id, "text_preview": amharic_text[:40]},
            )
            results[shot_id] = generated_path

        # Create combined full narration track from every shot clip on disk (not only this run's results)
        all_clips = {s["shot_id"]: self.output_dir / f"{s['shot_id']}.wav" for s in shots}
        all_clips.update(results)
        self._combine_narration_audio(shots, all_clips, self.output_dir / "full_narration.wav")

        if failed:
            details = "; ".join(f"{k}: {v}" for k, v in failed.items())
            raise RuntimeError(
                f"Narration failed for {len(failed)} shot(s) ({', '.join(failed)}). "
                f"Re-run `narration` to retry only those. {details}"
            )

        return results

    def _combine_narration_audio(
        self,
        shots: List[Dict[str, Any]],
        shot_audio_map: Dict[str, Path],
        full_audio_path: Path,
    ) -> None:
        """Combine per-shot narration into one track, aligned so each line starts with its shot.

        Each clip is padded with silence to the shot duration. A clip that runs slightly long is
        sped up (up to 1.25x) so it never spills into the next shot and sync is preserved.
        """
        import wave

        frames = []
        sample_rate, n_channels, samp_width = 24000, 1, 2
        for shot in shots:
            audio_path = shot_audio_map.get(shot["shot_id"])
            if audio_path and audio_path.is_file():
                try:
                    with wave.open(str(audio_path), "rb") as wf:
                        sample_rate = wf.getframerate()
                        n_channels = wf.getnchannels()
                        samp_width = wf.getsampwidth()
                except Exception:
                    pass
                else:
                    break

        for shot in shots:
            slot = float(shot.get("duration", 7.5))
            slot_frames = int(round(slot * sample_rate))
            audio_path = shot_audio_map.get(shot["shot_id"])
            data = b""
            if audio_path and audio_path.is_file():
                try:
                    data = self._fit_to_slot(audio_path, slot, sample_rate, n_channels, samp_width)
                except Exception:
                    data = b""
            frame_bytes = n_channels * samp_width
            want = slot_frames * frame_bytes
            data = data[:want] + bytes(1) * max(0, want - len(data))
            frames.append(data)

        with wave.open(str(full_audio_path), "wb") as out_wf:
            out_wf.setnchannels(n_channels)
            out_wf.setsampwidth(samp_width)
            out_wf.setframerate(sample_rate)
            for f in frames:
                out_wf.writeframes(f)

    @staticmethod
    def _fit_to_slot(audio_path: Path, slot: float, sample_rate: int, n_channels: int, samp_width: int) -> bytes:
        """Return PCM bytes for a clip, sped up if it is longer than its shot slot."""
        import subprocess
        import tempfile
        import wave
        from pipeline.utils.ffmpeg import is_ffmpeg_available

        with wave.open(str(audio_path), "rb") as wf:
            length = wf.getnframes() / float(wf.getframerate())
            raw = wf.readframes(wf.getnframes())
            src_rate = wf.getframerate()
        if length <= slot or not is_ffmpeg_available():
            return raw if src_rate == sample_rate else raw
        rate = min(1.25, length / slot * 1.01)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "fit.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio_path),
                 "-af", f"atempo={rate:.4f}", "-ar", str(sample_rate), "-ac", str(n_channels), "-c:a", "pcm_s16le", str(out)],
                check=True,
            )
            with wave.open(str(out), "rb") as wf:
                return wf.readframes(wf.getnframes())
