"""Gemini API provider for story refinement, translation, and Amharic TTS."""

import json
from pathlib import Path
import time
from typing import Any, Dict, Optional
import requests
from pipeline.config import GeminiConfig, get_config
from pipeline.logger import get_logger
from pipeline.providers.base import (
    AuthenticationError,
    BaseProvider,
    ProviderError,
    RateLimitError,
    TransientProviderError,
    retry_with_backoff,
)


class GeminiProvider(BaseProvider):
    def __init__(self, config: Optional[GeminiConfig] = None):
        self.config = config or get_config().gemini
        self.logger = get_logger()

    def verify_connection(self) -> Dict[str, Any]:
        """Perform a minimal smoke test for Gemini API."""
        if not self.config.is_configured:
            return {
                "provider": "gemini",
                "status": "UNCONFIGURED",
                "message": "GEMINI_API_KEY is not set or contains template value.",
            }

        url = f"{self.config.api_endpoint}/models/{self.config.text_model}?key={self.config.api_key}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return {
                    "provider": "gemini",
                    "status": "READY",
                    "model": self.config.text_model,
                    "message": "Gemini API connection verified successfully.",
                }
            elif resp.status_code in (401, 403):
                return {
                    "provider": "gemini",
                    "status": "AUTH_FAILED",
                    "message": f"Gemini API authentication failed (HTTP {resp.status_code}): {resp.text}",
                }
            else:
                return {
                    "provider": "gemini",
                    "status": "ERROR",
                    "message": f"Gemini API check returned HTTP {resp.status_code}: {resp.text}",
                }
        except Exception as exc:
            return {
                "provider": "gemini",
                "status": "NETWORK_ERROR",
                "message": f"Failed to connect to Gemini API: {exc}",
            }

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Gemini to generate or refine text."""
        if not self.config.is_configured:
            raise AuthenticationError("Cannot call Gemini API: GEMINI_API_KEY is not configured.")

        url = f"{self.config.api_endpoint}/models/{self.config.text_model}:generateContent?key={self.config.api_key}"
        headers = {"Content-Type": "application/json"}
        
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will follow these instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        body = {
            "contents": contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2048},
        }

        start_time = time.time()

        def _call():
            resp = requests.post(url, headers=headers, json=body, timeout=30)
            if resp.status_code in (401, 403):
                raise AuthenticationError(f"Gemini authentication failed: {resp.text}")
            if resp.status_code == 429:
                raise RateLimitError("Gemini rate limit exceeded.")
            if resp.status_code >= 500:
                raise TransientProviderError(f"Gemini server error: {resp.status_code}")
            if resp.status_code != 200:
                raise ProviderError(f"Gemini API error {resp.status_code}: {resp.text}")
            return resp.json()

        try:
            data = retry_with_backoff(_call)
            duration = time.time() - start_time
            result_text = data["candidates"][0]["content"]["parts"][0]["text"]
            self.logger.log(
                stage="script",
                provider="gemini",
                model=self.config.text_model,
                status="SUCCESS",
                prompt=prompt[:200],
                execution_duration_sec=duration,
            )
            return result_text
        except Exception as exc:
            duration = time.time() - start_time
            self.logger.log(
                stage="script",
                provider="gemini",
                model=self.config.text_model,
                status="FAILED",
                prompt=prompt[:200],
                execution_duration_sec=duration,
                error_details=str(exc),
            )
            raise

    def generate_amharic_tts(
        self,
        amharic_text: str,
        output_audio_path: str | Path,
        voice_name: str = "am-ET-Standard-A",
        mock_if_unconfigured: bool = False,
    ) -> Path:
        """Generate Amharic speech audio."""
        out_path = Path(output_audio_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.config.is_configured:
            if mock_if_unconfigured:
                # Create a lightweight valid silent or sine WAV placeholder for offline testing
                self._write_mock_audio(out_path)
                return out_path
            raise AuthenticationError("Gemini TTS is not configured. Provide GEMINI_API_KEY in .env.")

        # In production, call Gemini audio / Cloud Text-to-Speech API
        url = f"{self.config.api_endpoint}/models/{self.config.tts_model}:generateContent?key={self.config.api_key}"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [{"parts": [{"text": f"Read the following Amharic narration clearly and warmly: {amharic_text}"}]}],
            "generationConfig": {"responseMimeType": "audio/mp3"},
        }

        start_time = time.time()

        def _call():
            resp = requests.post(url, headers=headers, json=body, timeout=30)
            if resp.status_code in (401, 403):
                raise AuthenticationError(f"Gemini TTS authentication failed: {resp.text}")
            if resp.status_code != 200:
                raise ProviderError(f"Gemini TTS error {resp.status_code}: {resp.text}")
            return resp.content

        try:
            audio_bytes = retry_with_backoff(_call)
            duration = time.time() - start_time
            out_path.write_bytes(audio_bytes)
            self.logger.log(
                stage="narration",
                provider="gemini",
                model=self.config.tts_model,
                status="SUCCESS",
                prompt=amharic_text[:100],
                output_paths=[str(out_path)],
                execution_duration_sec=duration,
            )
            return out_path
        except Exception as exc:
            duration = time.time() - start_time
            self.logger.log(
                stage="narration",
                provider="gemini",
                model=self.config.tts_model,
                status="FAILED",
                prompt=amharic_text[:100],
                execution_duration_sec=duration,
                error_details=str(exc),
            )
            raise

    @staticmethod
    def _write_mock_audio(path: Path) -> None:
        """Generate a minimal valid 1-second silent WAV file for offline testing."""
        import wave
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(24000)
            wav_file.writeframes(b"\x00\x00" * 24000)  # 1 second silence

