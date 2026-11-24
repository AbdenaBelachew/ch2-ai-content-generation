"""Centralized pipeline configuration.

Loads settings from environment variables and .env file.
No model IDs or API endpoints are hardcoded throughout the pipeline.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class GeminiConfig:
    api_key: Optional[str] = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    text_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL_TEXT", "gemini-2.5-flash"))
    tts_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL_TTS", "gemini-2.5-flash-tts"))
    api_endpoint: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_ENDPOINT", "https://generativelanguage.googleapis.com/v1beta")
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))


@dataclass(frozen=True)
class CloudflareConfig:
    account_id: Optional[str] = field(default_factory=lambda: os.getenv("CLOUDFLARE_ACCOUNT_ID"))
    api_token: Optional[str] = field(default_factory=lambda: os.getenv("CLOUDFLARE_API_TOKEN"))
    flux_model: str = field(
        default_factory=lambda: os.getenv("CLOUDFLARE_FLUX_MODEL", "@cf/black-forest-labs/flux-1-schnell")
    )
    api_base: str = field(
        default_factory=lambda: os.getenv("CLOUDFLARE_API_BASE", "https://api.cloudflare.com/client/v4/accounts")
    )

    @property
    def is_configured(self) -> bool:
        return bool(
            self.account_id
            and self.api_token
            and not self.account_id.startswith("your_")
            and not self.api_token.startswith("your_")
        )

    @property
    def endpoint_url(self) -> str:
        return f"{self.api_base}/{self.account_id}/ai/run/{self.flux_model}"


@dataclass(frozen=True)
class KaggleConfig:
    username: Optional[str] = field(default_factory=lambda: os.getenv("KAGGLE_USERNAME"))
    key: Optional[str] = field(default_factory=lambda: os.getenv("KAGGLE_KEY"))
    wan_notebook_slug: str = field(
        default_factory=lambda: os.getenv("KAGGLE_WAN_NOTEBOOK_SLUG", "username/wan-2-2-ti2v-heritage-short")
    )
    acestep_notebook_slug: str = field(
        default_factory=lambda: os.getenv("KAGGLE_ACESTEP_NOTEBOOK_SLUG", "username/ace-step-music-heritage-short")
    )

    @property
    def is_configured(self) -> bool:
        return bool(
            self.username
            and self.key
            and not self.username.startswith("your_")
            and not self.key.startswith("your_")
        )


@dataclass(frozen=True)
class FFmpegConfig:
    ffmpeg_path: str = field(default_factory=lambda: os.getenv("FFMPEG_PATH", "ffmpeg"))
    ffprobe_path: str = field(default_factory=lambda: os.getenv("FFPROBE_PATH", "ffprobe"))


@dataclass
class PipelineConfig:
    base_dir: Path = field(default_factory=lambda: Path(os.getcwd()))
    storyboard_path: Path = field(default_factory=lambda: Path("storyboard.json"))
    schema_path: Path = field(default_factory=lambda: Path("schema/storyboard.schema.json"))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "outputs")))
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("CACHE_DIR", ".cache")))
    runs_log_path: Path = field(default_factory=lambda: Path(os.getenv("RUNS_LOG_PATH", "runs.jsonl")))
    
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    cloudflare: CloudflareConfig = field(default_factory=CloudflareConfig)
    kaggle: KaggleConfig = field(default_factory=KaggleConfig)
    ffmpeg: FFmpegConfig = field(default_factory=FFmpegConfig)

    def __post_init__(self):
        # Resolve paths relative to base_dir if relative
        if not self.storyboard_path.is_absolute():
            self.storyboard_path = self.base_dir / self.storyboard_path
        if not self.schema_path.is_absolute():
            self.schema_path = self.base_dir / self.schema_path
        if not self.output_dir.is_absolute():
            self.output_dir = self.base_dir / self.output_dir
        if not self.cache_dir.is_absolute():
            self.cache_dir = self.base_dir / self.cache_dir
        if not self.runs_log_path.is_absolute():
            self.runs_log_path = self.base_dir / self.runs_log_path


_CONFIG: Optional[PipelineConfig] = None


def get_config() -> PipelineConfig:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = PipelineConfig()
    return _CONFIG


def set_config(config: PipelineConfig) -> None:
    global _CONFIG
    _CONFIG = config

