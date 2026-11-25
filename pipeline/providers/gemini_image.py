"""Gemini image provider: keyframe / character sheet fallback when Cloudflare FLUX is unavailable."""

import base64
import os
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any, Dict, Optional
import requests
from pipeline.config import get_config
from pipeline.providers.base import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
    TransientProviderError,
    retry_with_backoff,
)
from pipeline.providers.cloudflare import CloudflareWorkersAIProvider


class GeminiImageProvider(CloudflareWorkersAIProvider):
    """Drop-in replacement for the Cloudflare provider that uses Gemini image generation.

    Reuses generate_character_sheet() from the parent, which builds its prompt and calls generate_image().
    """

    def __init__(self, model: Optional[str] = None):
        super().__init__(config=SimpleNamespace(flux_model="x", is_configured=False))
        gem = get_config().gemini
        self.gemini = gem
        self.config = SimpleNamespace(
            flux_model=model or os.getenv("GEMINI_MODEL_IMAGE", "gemini-2.5-flash-image"),
            is_configured=gem.is_configured,
        )

    def generate_image(
        self,
        prompt: str,
        output_image_path: str | Path,
        shot_id: Optional[str] = None,
        num_steps: int = 4,
        seed: Optional[int] = None,
        mock_if_unconfigured: bool = False,
    ) -> Path:
        out_path = Path(output_image_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.config.is_configured:
            if mock_if_unconfigured:
                self._write_mock_image(out_path)
                return out_path
            raise AuthenticationError("Gemini image generation is not configured. Set GEMINI_API_KEY in .env.")

        url = (
            f"{self.gemini.api_endpoint}/models/{self.config.flux_model}:generateContent"
            f"?key={self.gemini.api_key}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt + " Wide 16:9 cinematic frame."}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        start = time.time()

        def _call() -> bytes:
            resp = requests.post(url, json=body, timeout=120)
            if resp.status_code in (401, 403):
                raise AuthenticationError(f"Gemini image authentication failed: {resp.text}")
            if resp.status_code == 429:
                raise RateLimitError(f"Gemini image rate limited: {resp.text[:300]}")
            if resp.status_code >= 500:
                raise TransientProviderError(f"Gemini image server error: {resp.status_code}")
            if resp.status_code != 200:
                raise ProviderError(f"Gemini image error {resp.status_code}: {resp.text[:300]}")
            for cand in resp.json().get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        return base64.b64decode(inline["data"])
            raise ProviderError(f"Gemini returned no image: {resp.text[:300]}")

        try:
            out_path.write_bytes(retry_with_backoff(_call))
            self.logger.log(
                stage="keyframes",
                provider="gemini",
                model=self.config.flux_model,
                status="SUCCESS",
                shot_id=shot_id,
                prompt=prompt[:200],
                output_paths=[str(out_path)],
                execution_duration_sec=time.time() - start,
            )
            return out_path
        except Exception as exc:
            self.logger.log(
                stage="keyframes",
                provider="gemini",
                model=self.config.flux_model,
                status="FAILED",
                shot_id=shot_id,
                prompt=prompt[:200],
                execution_duration_sec=time.time() - start,
                error_details=str(exc),
            )
            raise
