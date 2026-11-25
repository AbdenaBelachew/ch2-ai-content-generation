"""Stage 6: Final Video Assembly & Radio Cut via FFmpeg."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.config import get_config
from pipeline.logger import get_logger
from pipeline.utils.ffmpeg import (
    build_end_card_command,
    build_final_assembly_command,
    build_radio_cut_command,
    build_scaled_concat_command,
    execute_ffmpeg,
    generate_srt,
    is_ffmpeg_available,
    synthesize_fallback_ducked_mix,
)
from pipeline.validator import load_json


class AssemblyStage:
    def __init__(self, dry_run: bool = False):
        self.config = get_config()
        self.logger = get_logger()
        self.dry_run = dry_run
        self.output_dir = self.config.output_dir / "assembly"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir = self.config.output_dir / "exports"
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def assemble_radio_cut(
        self,
        storyboard_path: Optional[str | Path] = None,
    ) -> Dict[str, Any]:
        """Mix narration audio with background music under sidechain ducking into a Radio Cut scratch mix."""
        path = Path(storyboard_path or self.config.storyboard_path)
        storyboard = load_json(path)
        music_settings = storyboard.get("music_settings", {})
        ducking_db = float(music_settings.get("ducking_attenuation_db", -14.0))

        narration_path = self.config.output_dir / "narration" / "full_narration.wav"
        music_path = self.config.output_dir / "music" / "soundtrack.wav"
        radio_cut_path = self.output_dir / "radio_cut.wav"

        if not narration_path.is_file() or not music_path.is_file():
            return {
                "status": "MISSING_PREREQUISITES",
                "message": "Both narration and music must be generated before building the Radio Cut.",
                "missing": {
                    "narration": not narration_path.is_file(),
                    "music": not music_path.is_file(),
                },
            }

        cmd = build_radio_cut_command(
            narration_audio_path=narration_path,
            music_audio_path=music_path,
            output_audio_path=radio_cut_path,
            ducking_attenuation_db=ducking_db,
        )

        if not self.dry_run:
            if is_ffmpeg_available():
                try:
                    execute_ffmpeg(cmd)
                except Exception:
                    synthesize_fallback_ducked_mix(narration_path, music_path, radio_cut_path)
            else:
                synthesize_fallback_ducked_mix(narration_path, music_path, radio_cut_path)

        self.logger.log(
            stage="radio",
            provider="ffmpeg" if is_ffmpeg_available() else "python_synth",
            model="sidechain_compressor",
            status="SUCCESS" if radio_cut_path.exists() else "DRY_RUN",
            output_paths=[str(radio_cut_path)],
            generation_parameters={"ducking_db": ducking_db},
        )

        return {
            "status": "SUCCESS" if radio_cut_path.exists() else "DRY_RUN",
            "radio_cut_path": str(radio_cut_path),
            "command": cmd,
        }

    def run(
        self,
        storyboard_path: Optional[str | Path] = None,
        aspect_ratios: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Assemble final video exports for specified aspect ratios."""
        path = Path(storyboard_path or self.config.storyboard_path)
        storyboard = load_json(path)
        shots = storyboard.get("shots", [])
        end_card_settings = storyboard.get("end_card_settings", {})
        music_settings = storyboard.get("music_settings", {})
        target_ratios = aspect_ratios or storyboard.get("output_aspect_ratios", ["9:16", "16:9"])

        # 1. Generate subtitles SRT
        srt_path = self.output_dir / "subtitles.srt"
        generate_srt(shots, srt_path)

        # 2. Check prerequisites
        shots_dir = self.config.output_dir / "shots"
        missing_shots = [
            s["shot_id"]
            for s in shots
            if not (shots_dir / f"{s['shot_id']}.mp4").exists()
        ]

        narration_path = self.config.output_dir / "narration" / "full_narration.wav"
        music_path = self.config.output_dir / "music" / "soundtrack.wav"

        ducking_db = float(music_settings.get("ducking_attenuation_db", -14.0))

        results: Dict[str, Any] = {
            "subtitles_srt": str(srt_path),
            "missing_inputs": {
                "shots": missing_shots,
                "narration": not narration_path.exists(),
                "music": not music_path.exists(),
            },
            "commands": {},
            "exports": {},
        }

        # Build end-card and assembly commands for each target aspect ratio
        for aspect in target_ratios:
            ratio_slug = aspect.replace(":", "x")
            end_card_clip = self.output_dir / f"end_card_{ratio_slug}.mp4"
            end_card_cmd = build_end_card_command(
                title=end_card_settings.get("title", "AI Heritage Short"),
                disclosure_text=end_card_settings.get(
                    "disclosure_text",
                    "This film was generated using an AI filmmaking pipeline.",
                ),
                duration=float(end_card_settings.get("duration_seconds", 4.0)),
                output_video_path=end_card_clip,
                aspect_ratio=aspect,
                bg_color=end_card_settings.get("background_color", "black"),
                font_color=end_card_settings.get("font_color", "white"),
            )
            results["commands"][f"end_card_{ratio_slug}"] = end_card_cmd

            export_file = self.exports_dir / f"film_{ratio_slug}.mp4"
            # Concatenate all shots + end card (normalized to this aspect ratio) into one silent video
            concat_video = self.output_dir / f"concat_{ratio_slug}.mp4"
            concat_inputs = [shots_dir / f"{s['shot_id']}.mp4" for s in shots] + [end_card_clip]
            concat_cmd = build_scaled_concat_command(concat_inputs, concat_video, aspect)
            results["commands"][f"concat_{ratio_slug}"] = concat_cmd

            assembly_cmd = build_final_assembly_command(
                video_input_path=concat_video,
                narration_audio_path=narration_path,
                music_audio_path=music_path,
                output_path=export_file,
                aspect_ratio=aspect,
                subtitles_srt_path=srt_path,
                ducking_attenuation_db=ducking_db,
            )
            results["commands"][f"assembly_{ratio_slug}"] = assembly_cmd

            if not self.dry_run and not missing_shots and narration_path.exists() and music_path.exists():
                if is_ffmpeg_available():
                    execute_ffmpeg(end_card_cmd)
                    execute_ffmpeg(concat_cmd)
                    execute_ffmpeg(assembly_cmd)
                    results["exports"][aspect] = str(export_file)
                else:
                    results["exports"][aspect] = "FFMPEG_NOT_FOUND_ON_SYSTEM"
            else:
                results["exports"][aspect] = "PENDING_PREREQUISITES"

        self.logger.log(
            stage="assemble",
            provider="ffmpeg",
            model="ffmpeg-7",
            status="SUCCESS" if not missing_shots else "PENDING_INPUTS",
            generation_parameters={"aspect_ratios": target_ratios, "ducking_db": ducking_db},
            output_paths=[str(self.exports_dir / f"film_{r.replace(':', 'x')}.mp4") for r in target_ratios],
        )

        return results
