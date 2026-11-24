"""Stage 1: Storyboard and Script Validation & Refinement."""

from pathlib import Path
from typing import Any, Dict, Optional
from pipeline.config import get_config
from pipeline.logger import get_logger
from pipeline.providers.gemini import GeminiProvider
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
            # Refinement is optional; we log the call if executed
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

