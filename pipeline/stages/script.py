"""Stage 1: Storyboard and Script Validation & Refinement."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.config import get_config
from pipeline.logger import get_logger
from pipeline.providers.gemini import GeminiProvider, analyze_amharic_script
from pipeline.validator import StoryboardValidationError, load_json, validate_storyboard_dict


class ScriptStage:
    def __init__(self, gemini_provider: Optional[GeminiProvider] = None):
        self.config = get_config()
        self.logger = get_logger()
        self.provider = gemini_provider or GeminiProvider()

    def run(self, refine: bool = False, storyboard_path: Optional[str | Path] = None) -> Dict[str, Any]:
        """Validate single source of truth storyboard and optionally refine text."""
        path = Path(storyboard_path or self.config.storyboard_path)
        if not path.is_file():
            raise FileNotFoundError(f"Storyboard not found at {path}")

        storyboard = load_json(path)
        valid, errors = validate_storyboard_dict(storyboard)
        if not valid:
            raise StoryboardValidationError(errors)

        if refine and self.provider.config.is_configured:
            prompt = (
                f"Review and refine the Amharic poetic narration and English translations "
                f"for the film '{storyboard.get('film_title')}'. Return refined JSON.\n"
                f"Current storyboard: {storyboard}"
            )
            try:
                self.provider.generate_text(prompt)
            except Exception as exc:
                self.logger.log(
                    stage="script",
                    provider="gemini",
                    model=self.provider.config.text_model,
                    status="FAILED",
                    prompt=prompt[:200],
                    error_details=str(exc),
                )

        self.logger.log(
            stage="script",
            provider="local",
            model="validator",
            status="SUCCESS",
            prompt=f"Validated storyboard {path.name}",
            generation_parameters={"total_shots": len(storyboard.get("shots", []))},
        )
        return storyboard

    def analyze_pacing(self, storyboard_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
        """Analyze narration pacing and syllable counts for all shots."""
        path = Path(storyboard_path or self.config.storyboard_path)
        storyboard = load_json(path)
        shots = storyboard.get("shots", [])

        report = []
        for shot in shots:
            shot_id = shot["shot_id"]
            duration = float(shot.get("duration", 7.5))
            amharic_text = shot.get("narration_amharic", "")
            metrics = analyze_amharic_script(amharic_text)
            est_duration = metrics["estimated_duration_sec"]

            # Flag if narration is estimated to take longer than shot duration
            is_rushed = est_duration > duration
            report.append({
                "shot_id": shot_id,
                "duration": duration,
                "fidel_count": metrics["fidel_count"],
                "word_count": metrics["word_count"],
                "estimated_duration_sec": est_duration,
                "is_rushed": is_rushed,
                "headroom_sec": round(duration - est_duration, 2),
            })

        return report
