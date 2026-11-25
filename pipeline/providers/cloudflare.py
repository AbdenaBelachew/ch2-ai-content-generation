"""Cloudflare Workers AI provider for FLUX-1 Schnell keyframe and character sheet generation."""

import base64
from pathlib import Path
import time
from typing import Any, Dict, Optional
import requests
from pipeline.config import CloudflareConfig, get_config
from pipeline.logger import get_logger
from pipeline.providers.base import (
    AuthenticationError,
    BaseProvider,
    ProviderError,
    RateLimitError,
    TransientProviderError,
    retry_with_backoff,
)


class CloudflareWorkersAIProvider(BaseProvider):
    def __init__(self, config: Optional[CloudflareConfig] = None):
        self.config = config or get_config().cloudflare
        self.logger = get_logger()

    def verify_connection(self) -> Dict[str, Any]:
        """Perform a minimal smoke test for Cloudflare Workers AI."""
        if not self.config.is_configured:
            return {
                "provider": "cloudflare",
                "status": "UNCONFIGURED",
                "message": "CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is not set.",
            }

        headers = {"Authorization": f"Bearer {self.config.api_token}"}
        # Account-owned tokens verify under /accounts/{id}/tokens/verify, user tokens under /user/tokens/verify.
        try:
            base = "https://api.cloudflare.com/client/v4"
            resp = requests.get(f"{base}/accounts/{self.config.account_id}/tokens/verify", headers=headers, timeout=10)
            if resp.status_code in (401, 403):
                resp = requests.get(f"{base}/user/tokens/verify", headers=headers, timeout=10)
            if resp.status_code == 200:
                return {
                    "provider": "cloudflare",
                    "status": "READY",
                    "model": self.config.flux_model,
                    "message": "Cloudflare API token verified successfully.",
                }
            elif resp.status_code in (401, 403):
                return {
                    "provider": "cloudflare",
                    "status": "AUTH_FAILED",
                    "message": f"Cloudflare token unauthorized (HTTP {resp.status_code}): {resp.text}",
                }
            else:
                return {
                    "provider": "cloudflare",
                    "status": "ERROR",
                    "message": f"Cloudflare check returned HTTP {resp.status_code}: {resp.text}",
                }
        except Exception as exc:
            return {
                "provider": "cloudflare",
                "status": "NETWORK_ERROR",
                "message": f"Failed to connect to Cloudflare Workers AI: {exc}",
            }

    def generate_image(
        self,
        prompt: str,
        output_image_path: str | Path,
        shot_id: Optional[str] = None,
        num_steps: int = 4,
        seed: Optional[int] = None,
        mock_if_unconfigured: bool = False,
    ) -> Path:
        """Call Cloudflare FLUX-1 Schnell to generate an image."""
        out_path = Path(output_image_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.config.is_configured:
            if mock_if_unconfigured:
                self._write_mock_image(out_path)
                return out_path
            raise AuthenticationError("Cloudflare Workers AI is not configured. Set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in .env.")

        headers = {
            "Authorization": f"Bearer {self.config.api_token}",
            "Content-Type": "application/json",
        }
        body: Dict[str, Any] = {
            "prompt": prompt,
            "steps": max(1, min(int(num_steps), 8)),  # flux-1-schnell accepts 'steps' (max 8)
        }
        # Note: the current flux-1-schnell schema rejects 'seed', so it is only logged/cached, not sent.

        start_time = time.time()

        def _call():
            resp = requests.post(self.config.endpoint_url, headers=headers, json=body, timeout=60)
            if resp.status_code in (401, 403):
                raise AuthenticationError(f"Cloudflare authentication failed: {resp.text}")
            if resp.status_code == 429:
                raise RateLimitError("Cloudflare Workers AI rate limit exceeded.")
            if resp.status_code >= 500:
                raise TransientProviderError(f"Cloudflare Workers AI server error: {resp.status_code}")
            if resp.status_code != 200:
                raise ProviderError(f"Cloudflare API error {resp.status_code}: {resp.text}")
            return resp

        try:
            resp = retry_with_backoff(_call)
            duration = time.time() - start_time

            # Cloudflare FLUX returns raw image bytes or JSON with image base64
            content_type = resp.headers.get("content-type", "")
            if "image" in content_type:
                out_path.write_bytes(resp.content)
            else:
                data = resp.json()
                if "result" in data and "image" in data["result"]:
                    img_bytes = base64.b64decode(data["result"]["image"])
                    out_path.write_bytes(img_bytes)
                else:
                    out_path.write_bytes(resp.content)

            self.logger.log(
                stage="keyframes",
                provider="cloudflare",
                model=self.config.flux_model,
                status="SUCCESS",
                shot_id=shot_id,
                prompt=prompt[:200],
                generation_parameters={"steps": num_steps},
                seed=seed,
                output_paths=[str(out_path)],
                execution_duration_sec=duration,
            )
            return out_path
        except Exception as exc:
            duration = time.time() - start_time
            self.logger.log(
                stage="keyframes",
                provider="cloudflare",
                model=self.config.flux_model,
                status="FAILED",
                shot_id=shot_id,
                prompt=prompt[:200],
                generation_parameters={"steps": num_steps},
                seed=seed,
                execution_duration_sec=duration,
                error_details=str(exc),
            )
            raise

    def generate_character_sheet(
        self,
        character_data: Dict[str, Any],
        output_image_path: str | Path,
        seed: int = 42,
        mock_if_unconfigured: bool = False,
    ) -> Path:
        """Generate a multi-angle character turnaround reference sheet to ensure cross-shot visual consistency."""
        name = character_data.get("name", "Character")
        traits = character_data.get("visual_traits", {})
        age = traits.get("estimated_age", "72 years old")
        attire = traits.get("attire", "Habesha Kemis")
        facial = traits.get("facial_features", "warm features")
        hair = traits.get("hair", "traditional braids")

        prompt = (
            f"Professional character design turnaround model sheet for {name}, {age}. "
            f"Three distinct views on a single image: front view full body, three-quarter angle portrait, and close-up profile. "
            f"Attire: {attire}. Facial details: {facial}. Hair: {hair}. "
            f"Neutral studio grey background, even documentary lighting, cinematic photorealism, 8k resolution, perfect anatomical consistency."
        )

        return self.generate_image(
            prompt=prompt,
            output_image_path=output_image_path,
            shot_id="char_sheet",
            num_steps=8,
            seed=seed,
            mock_if_unconfigured=mock_if_unconfigured,
        )

    @staticmethod
    def _write_mock_image(path: Path) -> None:
        """Write a minimal valid 1x1 PNG image for offline testing."""
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        path.write_bytes(png_bytes)
