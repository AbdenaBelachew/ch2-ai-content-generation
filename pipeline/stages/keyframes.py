"""Stage 2: Keyframe Image Generation via Cloudflare Workers AI FLUX."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.cache import get_cache
from pipeline.config import get_config
from pipeline.logger import get_logger
from pipeline.providers.cloudflare import CloudflareWorkersAIProvider
from pipeline.validator import load_json


class KeyframesStage:
    def __init__(
        self,
        cloudflare_provider: Optional[CloudflareWorkersAIProvider] = None,
        mock_if_unconfigured: bool = False,
    ):
        self.config = get_config()
        self.cache = get_cache()
        self.logger = get_logger()
        self.provider = cloudflare_provider or CloudflareWorkersAIProvider()
        self.mock_if_unconfigured = mock_if_unconfigured
        self.output_dir = self.config.output_dir / "keyframes"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_character_sheets(
        self,
        storyboard_path: Optional[str | Path] = None,
        force_regenerate: bool = False,
    ) -> Dict[str, Path]:
        """Generate character turnaround reference sheets for all characters declared in storyboard."""
        path = Path(storyboard_path or self.config.storyboard_path)
        storyboard = load_json(path)
        characters = storyboard.get("character_references", [])
        results: Dict[str, Path] = {}

        for char in characters:
            cid = char["character_id"]
            out_file = self.output_dir / f"character_sheet_{cid}.png"
            cache_key = self.cache.keyframe_key(
                prompt=f"character_sheet_{cid}_{char.get('description', '')}",
                ref_image_path=None,
                model_id=self.provider.config.flux_model,
                generation_settings={"steps": 8, "type": "turnaround_sheet"},
                seed=42,
            )

            if not force_regenerate and self.cache.is_cached("keyframes", cache_key, out_file):
                self.logger.log(
                    stage="keyframes",
                    provider="cloudflare",
                    model=self.provider.config.flux_model,
                    status="CACHED",
                    shot_id=f"sheet_{cid}",
                    output_paths=[str(out_file)],
                )
                results[cid] = out_file
                continue

            generated = self.provider.generate_character_sheet(
                character_data=char,
                output_image_path=out_file,
                seed=42,
                mock_if_unconfigured=self.mock_if_unconfigured,
            )
            self.cache.put(
                stage="keyframes",
                cache_key=cache_key,
                output_path=generated,
                metadata={"character_id": cid, "type": "character_sheet"},
            )
            results[cid] = generated

        return results

    def run(
        self,
        storyboard_path: Optional[str | Path] = None,
        force_regenerate: bool = False,
        shot_ids: Optional[List[str]] = None,
        generate_sheets_first: bool = True,
    ) -> Dict[str, Path]:
        """Generate keyframe images for storyboard shots using cached outputs when available."""
        path = Path(storyboard_path or self.config.storyboard_path)
        storyboard = load_json(path)
        shots = storyboard.get("shots", [])

        # Step A: Ensure character sheets are generated first to act as visual anchor
        char_ref_images: Dict[str, str] = {}
        if generate_sheets_first and storyboard.get("character_references"):
            sheets = self.generate_character_sheets(path, force_regenerate=force_regenerate)
            for cid, sheet_path in sheets.items():
                char_ref_images[cid] = str(sheet_path)

        # Also incorporate any pre-existing reference image paths from storyboard
        for c in storyboard.get("character_references", []):
            cid = c.get("character_id")
            if cid and c.get("reference_image_path") and cid not in char_ref_images:
                char_ref_images[cid] = c["reference_image_path"]

        results: Dict[str, Path] = {}

        for shot in shots:
            shot_id = shot["shot_id"]
            if shot_ids and shot_id not in shot_ids:
                continue

            prompt = shot.get("image_prompt", "")
            gen_settings = shot.get("generation_settings", {})
            seed = gen_settings.get("seed")
            steps = gen_settings.get("steps", 4)
            model_id = self.provider.config.flux_model

            # Determine primary character ref image if referenced
            ref_img = None
            for cid in shot.get("character_reference_ids", []):
                if char_ref_images.get(cid):
                    ref_img = char_ref_images[cid]
                    break

            cache_key = self.cache.keyframe_key(
                prompt=prompt,
                ref_image_path=ref_img,
                model_id=model_id,
                generation_settings=gen_settings,
                seed=seed,
            )

            out_file = self.output_dir / f"{shot_id}.png"

            if not force_regenerate and self.cache.is_cached("keyframes", cache_key, out_file):
                self.logger.log(
                    stage="keyframes",
                    provider="cloudflare",
                    model=model_id,
                    status="CACHED",
                    shot_id=shot_id,
                    prompt_hash=cache_key,
                    seed=seed,
                    output_paths=[str(out_file)],
                )
                results[shot_id] = out_file
                continue

            # Generate via provider
            generated_path = self.provider.generate_image(
                prompt=prompt,
                output_image_path=out_file,
                shot_id=shot_id,
                num_steps=steps,
                seed=seed,
                mock_if_unconfigured=self.mock_if_unconfigured,
            )

            self.cache.put(
                stage="keyframes",
                cache_key=cache_key,
                output_path=generated_path,
                metadata={"shot_id": shot_id, "prompt": prompt[:100], "seed": seed, "ref_img": ref_img},
            )
            results[shot_id] = generated_path

        return results
