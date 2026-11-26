"""ACE-Step 1.5 music runner (Kaggle GPU).

Reads `acestep_batch.json`, generates ONE instrumental track with the real ACE-Step 1.5 model and
writes `soundtrack.wav` plus `music_report.json` (measured timings, seed, settings).

Honesty rules: no synthesised stand-in audio is ever written here. If the model cannot be loaded
or produces no audio, this script raises.

API notes (from ACE-Step docs/en/INFERENCE.md; NOT yet executed on a Kaggle GPU):
  from acestep.handler import AceStepHandler
  from acestep.llm_inference import LLMHandler
  from acestep.inference import GenerationParams, GenerationConfig, generate_music
The docs name `offload_to_cpu` / `quantization` for GPUs with <20 GB but do not show which call takes
them, so they are passed only if the installed signature accepts them (see `_supported_kwargs`).
"""

import argparse
import inspect
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DIT_CONFIG = "acestep-v15-turbo"
LM_MODEL = "acestep-5Hz-lm-0.6B"  # smallest LM; fits 16 GB alongside the DiT


def _supported_kwargs(fn, wanted: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only kwargs the installed function accepts, and say which were dropped."""
    params = inspect.signature(fn).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return wanted
    kept = {k: v for k, v in wanted.items() if k in params}
    dropped = sorted(set(wanted) - set(kept))
    if dropped:
        print(f"  note: {fn.__qualname__} does not accept {dropped}; skipped")
    return kept


def build_caption(settings: Dict[str, Any]) -> str:
    caption = settings.get("prompt", "").strip()
    inst = ", ".join(settings.get("instrumentation", []))
    mood = settings.get("mood", "")
    extra = [x for x in (inst and f"instruments: {inst}", mood and f"mood: {mood}") if x]
    caption = f"{caption} ({'; '.join(extra)})" if extra else caption
    return caption[:512]  # documented caption limit


def run_acestep(
    manifest_path: str,
    output_file: str,
    project_root: str,
    seed: int = 42,
    thinking: bool = True,
    lm_backend: str = "pt",
) -> Dict[str, Any]:
    import torch
    from acestep.handler import AceStepHandler
    from acestep.inference import GenerationConfig, GenerationParams, generate_music
    from acestep.llm_inference import LLMHandler

    if not torch.cuda.is_available():
        raise RuntimeError("No CUDA GPU. In Kaggle choose Accelerator -> GPU, then restart.")

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    s = manifest["music_settings"]
    duration = float(s.get("target_duration", 78.0)) + 4.0  # cover the 4 s end card too
    bpm = int(s.get("tempo_bpm", 68))
    caption = build_caption(s)
    print(f"Caption: {caption}\nDuration: {duration}s  BPM: {bpm}  seed: {seed}")

    t0 = time.time()
    dit = AceStepHandler()
    dit.initialize_service(**_supported_kwargs(dit.initialize_service, {
        "project_root": project_root,
        "config_path": DIT_CONFIG,
        "device": "cuda",
        "offload_to_cpu": True,
        "quantization": "int8_weight_only",
    }))
    llm = LLMHandler()
    llm.initialize(**_supported_kwargs(llm.initialize, {
        "checkpoint_dir": str(Path(project_root) / "checkpoints"),
        "lm_model_path": LM_MODEL,
        "backend": lm_backend,
        "device": "cuda",
    }))
    load_seconds = time.time() - t0

    params = GenerationParams(
        caption=caption,
        lyrics="[Instrumental]",
        instrumental=True,
        bpm=bpm,
        duration=duration,
        seed=seed,
        shift=3.0,  # docs: guidance auto-corrects for turbo but shift does not
        thinking=thinking,
    )
    config = GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=False, seeds=[seed])

    save_dir = Path(project_root) / "generated"
    save_dir.mkdir(parents=True, exist_ok=True)
    t1 = time.time()
    result = generate_music(dit, llm, params, config, save_dir=str(save_dir))
    gen_seconds = time.time() - t1
    if not result.success or not result.audios:
        raise RuntimeError(f"ACE-Step generation failed: {getattr(result, 'error', 'no audio returned')}")

    src = Path(result.audios[0]["path"])
    dst = Path(output_file)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    size = dst.stat().st_size
    if size < 100_000:
        raise RuntimeError(f"Soundtrack is only {size} bytes; refusing to report success.")

    report = {
        "model": f"ACE-Step-1.5 ({DIT_CONFIG} + {LM_MODEL})",
        "gpu": torch.cuda.get_device_name(0),
        "caption": caption,
        "duration_s": duration,
        "bpm": bpm,
        "seed": seed,
        "thinking": thinking,
        "lm_backend": lm_backend,
        "load_seconds": round(load_seconds, 1),
        "generate_seconds": round(gen_seconds, 1),
        "bytes": size,
        "sample_rate": result.audios[0].get("sample_rate"),
    }
    (dst.parent / "music_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Done: {dst} ({size/1e6:.1f} MB) in {gen_seconds:.0f}s")
    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="acestep_batch.json")
    ap.add_argument("--out", default="outputs/music/soundtrack.wav")
    ap.add_argument("--project-root", required=True, help="Path to the cloned ACE-Step-1.5 repo")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-thinking", action="store_true", help="Disable the LM planner (less VRAM, faster)")
    ap.add_argument("--lm-backend", default="pt", choices=["pt", "vllm"])
    a = ap.parse_args(argv)
    run_acestep(a.manifest, a.out, a.project_root, a.seed, not a.no_thinking, a.lm_backend)
    return 0


if __name__ == "__main__":
    sys.exit(main())
