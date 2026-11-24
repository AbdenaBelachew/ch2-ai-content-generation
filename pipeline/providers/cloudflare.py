"""Cloudflare Workers AI provider for FLUX-1 Schnell keyframe generation."""

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
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.config.account_id}/tokens/verify"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
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
            "num_steps": num_steps,
        }
        if seed is not None:
            body["seed"] = seed

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

    @staticmethod
    def _write_mock_image(path: Path) -> None:
        """Write a minimal valid 1x1 PNG image for offline testing."""
        # 1x1 transparent/black PNG
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        path.write_bytes(png_bytes)

