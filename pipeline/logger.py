"""Audit logging for model and pipeline invocations.

Appends run records in JSON Lines format to runs.jsonl.
Never invents cost, latency, or GPU usage measurements.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pipeline.config import get_config


@dataclass
class RunRecord:
    timestamp: str
    stage: str
    provider: str
    model: str
    status: str  # "SUCCESS", "FAILED", "CACHED", "SKIPPED"
    shot_id: Optional[str] = None
    prompt: Optional[str] = None
    prompt_hash: Optional[str] = None
    generation_parameters: Optional[Dict[str, Any]] = None
    seed: Optional[int] = None
    input_paths: Optional[List[str]] = None
    output_paths: Optional[List[str]] = None
    execution_duration_sec: Optional[float] = None
    gpu_minutes: Optional[float] = None
    cost_usd: Optional[float] = None
    error_details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


class PipelineLogger:
    def __init__(self, log_path: Optional[Path] = None):
        if log_path is None:
            log_path = get_config().runs_log_path
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_run(self, record: RunRecord) -> None:
        """Append a record to runs.jsonl in UTF-8."""
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def log(
        self,
        stage: str,
        provider: str,
        model: str,
        status: str,
        shot_id: Optional[str] = None,
        prompt: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        generation_parameters: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
        input_paths: Optional[List[str]] = None,
        output_paths: Optional[List[str]] = None,
        execution_duration_sec: Optional[float] = None,
        gpu_minutes: Optional[float] = None,
        cost_usd: Optional[float] = None,
        error_details: Optional[str] = None,
    ) -> RunRecord:
        """Create, record, and return a RunRecord."""
        record = RunRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage=stage,
            provider=provider,
            model=model,
            status=status,
            shot_id=shot_id,
            prompt=prompt,
            prompt_hash=prompt_hash,
            generation_parameters=generation_parameters,
            seed=seed,
            input_paths=input_paths,
            output_paths=output_paths,
            execution_duration_sec=execution_duration_sec,
            gpu_minutes=gpu_minutes,
            cost_usd=cost_usd,
            error_details=error_details,
        )
        self.log_run(record)
        return record


_LOGGER: Optional[PipelineLogger] = None


def get_logger() -> PipelineLogger:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = PipelineLogger()
    return _LOGGER

