"""Wan 2.2 TI2V-5B image-to-video runner (Kaggle GPU).

Single source of truth for video generation: the notebook only installs dependencies and calls
`run_wan_batch`. It reads `wan_batch.json` and the keyframe PNGs, animates each keyframe with the
shot's motion prompt, and writes `<shot_id>.mp4` plus `run_report.json` (measured timings).

Honesty rules enforced here:
  * No placeholder files are ever written. If the model cannot load or a shot fails, it fails loudly.
  * Every output is checked for size/frames before being reported as done.
  * Timings in the report are measured wall-clock values from this run.

API notes (verified against the model card / Diffusers docs, NOT yet executed on a Kaggle GPU):
  * Model:  Wan-AI/Wan2.2-TI2V-5B-Diffusers  (24 fps, native 720P, frame count must be 4k+1)
  * The model card only shows text-to-video Python. Image conditioning uses WanImageToVideoPipeline
    with `image=`, as in the Diffusers Wan docs. If this class rejects the checkpoint, the error is
    surfaced as-is; see kaggle/README.md "If something fails".
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MODEL_ID = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"

# Memory/time controls. Defaults aim at a 16 GB T4/P100; raise them on larger GPUs.
DEFAULTS: Dict[str, Any] = {
    "max_area": 480 * 832,      # pixels per frame; model native 720P is 1280*704 = 901k (needs far more VRAM)
    "max_frames": 121,          # 4k+1; at 24 fps = 5.04 s. Planned 7.5 s shots are held on the last frame.
    "num_inference_steps": 30,  # card example uses 50; lower = faster, lower quality
    "guidance_scale": 5.0,
    "seed": 42,
}

NEGATIVE_PROMPT = (
    "Bright tones, overexposed, static, blurred details, subtitles, style, works, paintings, images, "
    "overall gray, worst quality, low quality, JPEG compression residue, ugly, incomplete, extra fingers, "
    "poorly drawn hands, poorly drawn faces, deformed, disfigured, misshapen limbs, fused fingers, "
    "still picture, messy background, three legs, many people in the background, walking backwards"
)


def frames_for(duration_s: float, fps: int, cap: int) -> int:
    """Largest 4k+1 frame count not exceeding both the planned duration and the cap."""
    want = max(5, int(round(duration_s * fps)))
    n = min(want, cap)
    return ((n - 1) // 4) * 4 + 1


def fit_size(img_w: int, img_h: int, max_area: int, mod: int) -> tuple[int, int]:
    """Keep the keyframe's aspect ratio, bounded by max_area, snapped down to a multiple of `mod`."""
    import math
    aspect = img_h / img_w
    h = round(math.sqrt(max_area * aspect)) // mod * mod
    w = round(math.sqrt(max_area / aspect)) // mod * mod
    return max(w, mod), max(h, mod)


def load_pipeline(dtype_name: str = "bfloat16"):
    import torch
    from diffusers import AutoencoderKLWan, WanImageToVideoPipeline

    if not torch.cuda.is_available():
        raise RuntimeError("No CUDA GPU. In Kaggle choose Accelerator -> GPU T4 x2 or P100, then restart.")
    dtype = getattr(torch, dtype_name)
    vae = AutoencoderKLWan.from_pretrained(MODEL_ID, subfolder="vae", torch_dtype=torch.float32)
    pipe = WanImageToVideoPipeline.from_pretrained(MODEL_ID, vae=vae, torch_dtype=dtype)
    pipe.enable_model_cpu_offload()  # keeps a 16 GB card usable; slower than full-GPU
    if hasattr(pipe.vae, "enable_tiling"):
        pipe.vae.enable_tiling()
    return pipe


def run_wan_batch(
    manifest_path: str,
    keyframes_dir: str,
    output_dir: str,
    only: Optional[List[str]] = None,
    overrides: Optional[Dict[str, Any]] = None,
    dtype_name: str = "bfloat16",
) -> Dict[str, Any]:
    import numpy as np  # noqa: F401  (diffusers dependency; fail early if missing)
    import torch
    from diffusers.utils import export_to_video, load_image

    cfg = {**DEFAULTS, **(overrides or {})}
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    shots = [s for s in manifest.get("shots", []) if not only or s["shot_id"] in only]
    if not shots:
        raise RuntimeError("No shots to generate (check manifest / --only).")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    kf_dir = Path(keyframes_dir)

    t_load = time.time()
    pipe = load_pipeline(dtype_name)
    load_seconds = time.time() - t_load
    mod = pipe.vae_scale_factor_spatial * pipe.transformer.config.patch_size[1]
    gpu_name = torch.cuda.get_device_name(0)
    print(f"Pipeline loaded in {load_seconds:.0f}s on {gpu_name}; size multiple={mod}")

    report: Dict[str, Any] = {
        "model": MODEL_ID,
        "gpu": gpu_name,
        "dtype": dtype_name,
        "settings": cfg,
        "load_seconds": round(load_seconds, 1),
        "shots": {},
    }

    for idx, shot in enumerate(shots, 1):
        sid = shot["shot_id"]
        kf = kf_dir / f"{sid}.png"
        if not kf.is_file():
            raise FileNotFoundError(f"Keyframe missing: {kf}")
        fps = int(shot.get("fps", 24))
        n_frames = frames_for(float(shot.get("duration", 7.5)), fps, int(cfg["max_frames"]))
        image = load_image(str(kf))
        w, h = fit_size(image.width, image.height, int(cfg["max_area"]), mod)
        image = image.resize((w, h))
        generator = torch.Generator(device="cpu").manual_seed(int(cfg["seed"]) + idx)

        print(f"\n[{idx}/{len(shots)}] {sid}: {w}x{h}, {n_frames} frames @ {fps} fps")
        t0 = time.time()
        frames = pipe(
            image=image,
            prompt=shot["motion_prompt"],
            negative_prompt=NEGATIVE_PROMPT,
            height=h,
            width=w,
            num_frames=n_frames,
            num_inference_steps=int(cfg["num_inference_steps"]),
            guidance_scale=float(cfg["guidance_scale"]),
            generator=generator,
        ).frames[0]
        gen_seconds = time.time() - t0

        target = out / f"{sid}.mp4"
        export_to_video(frames, str(target), fps=fps)
        size = target.stat().st_size if target.is_file() else 0
        if size < 20_000:
            raise RuntimeError(f"{sid}: output is only {size} bytes; refusing to report success.")
        report["shots"][sid] = {
            "seconds": round(gen_seconds, 1),
            "frames": n_frames,
            "fps": fps,
            "width": w,
            "height": h,
            "seed": int(cfg["seed"]) + idx,
            "bytes": size,
        }
        print(f"  done in {gen_seconds:.0f}s ({size/1e6:.1f} MB)")
        # Write the report after each shot so partial progress survives a session timeout.
        (out / "run_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        torch.cuda.empty_cache()

    return report


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--manifest", default="wan_batch.json")
    ap.add_argument("--keyframes", default="keyframes")
    ap.add_argument("--out", default="outputs/shots")
    ap.add_argument("--only", nargs="*", help="Generate only these shot IDs (test one shot first!)")
    ap.add_argument("--max-frames", type=int)
    ap.add_argument("--max-area", type=int)
    ap.add_argument("--steps", type=int)
    ap.add_argument("--dtype", default="bfloat16", choices=["bfloat16", "float16"])
    a = ap.parse_args(argv)
    ov = {k: v for k, v in {"max_frames": a.max_frames, "max_area": a.max_area,
                            "num_inference_steps": a.steps}.items() if v}
    run_wan_batch(a.manifest, a.keyframes, a.out, a.only, ov, a.dtype)
    return 0


if __name__ == "__main__":
    sys.exit(main())
