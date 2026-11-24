"""Stage 6: Final Video Assembly via FFmpeg."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.config import get_config
from pipeline.logger import get_logger
from pipeline.utils.ffmpeg import (
    build_end_card_command,
    build_final_assembly_command,
    execute_ffmpeg,
    generate_srt,
    is_ffmpeg_available,
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
            # Video concat source: for test/dry-run, we use shot_01 or placeholder
            sample_video = shots_dir / f"{shots[0]['shot_id']}.mp4" if shots else shots_dir / "shot_01.mp4"
            
            assembly_cmd = build_final_assembly_command(
                video_input_path=sample_video,
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

