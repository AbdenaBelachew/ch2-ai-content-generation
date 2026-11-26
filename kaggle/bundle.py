"""Prepare Kaggle inputs (`pack`) and import Kaggle outputs (`unpack`).

  python kaggle/bundle.py pack            # -> outputs/kaggle_bundle/ (+ .zip) to upload as a Kaggle dataset
  python kaggle/bundle.py unpack FILE...  # FILE = outputs_shots.zip / soundtrack bundle zip / directory

`unpack` validates every file (rejects placeholders), copies it into outputs/, registers it in the
cache, and appends a runs.jsonl record using ONLY the timings the Kaggle run measured.
"""

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.cache import get_cache  # noqa: E402
from pipeline.config import get_config  # noqa: E402
from pipeline.logger import get_logger  # noqa: E402
from pipeline.utils.media import audio_problem, video_problem  # noqa: E402
from pipeline.validator import load_json  # noqa: E402

BUNDLE = ROOT / "outputs" / "kaggle_bundle"
WAN_MODEL_ID = "Wan2.2-TI2V-5B"
MUSIC_MODEL_ID = "ACE-Step-1.5"


def pack() -> int:
    cfg = get_config()
    sb = load_json(cfg.storyboard_path)
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    (BUNDLE / "keyframes").mkdir(parents=True)

    shots = []
    for s in sb["shots"]:
        sid = s["shot_id"]
        kf = cfg.output_dir / "keyframes" / f"{sid}.png"
        if not kf.is_file():
            print(f"ERROR: missing keyframe {kf}. Run `python -m pipeline.cli keyframes` first.")
            return 1
        shutil.copyfile(kf, BUNDLE / "keyframes" / kf.name)
        shots.append({
            "shot_id": sid,
            "motion_prompt": s.get("motion_prompt", ""),
            "duration": s.get("duration", 7.5),
            "camera_movement": s.get("camera_movement", ""),
            "fps": s.get("generation_settings", {}).get("fps", 24),
        })
    (BUNDLE / "wan_batch.json").write_text(
        json.dumps({"model": WAN_MODEL_ID, "shots": shots}, indent=2, ensure_ascii=False), encoding="utf-8")
    (BUNDLE / "acestep_batch.json").write_text(
        json.dumps({"model": MUSIC_MODEL_ID, "music_settings": sb["music_settings"]}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    for runner in ("wan2_ti2v_runner.py", "ace_step_runner.py"):
        shutil.copyfile(ROOT / "kaggle" / runner, BUNDLE / runner)

    zip_path = shutil.make_archive(str(BUNDLE), "zip", BUNDLE)
    print(f"Bundle ready: {BUNDLE}\nZip: {zip_path}")
    print("Upload the folder contents as a Kaggle dataset named `heritage-short-inputs`.")
    return 0


def _extract(src: Path, tmp: Path) -> Path:
    if src.is_dir():
        return src
    with zipfile.ZipFile(src) as z:
        z.extractall(tmp)
    return tmp


def unpack(sources: list[str]) -> int:
    cfg = get_config()
    cache, logger = get_cache(), get_logger()
    sb = load_json(cfg.storyboard_path)
    shots = {s["shot_id"]: s for s in sb["shots"]}
    shots_dir = cfg.output_dir / "shots"
    music_dir = cfg.output_dir / "music"
    shots_dir.mkdir(parents=True, exist_ok=True)
    music_dir.mkdir(parents=True, exist_ok=True)
    bad = 0

    for source in sources:
        with tempfile.TemporaryDirectory() as t:
            base = _extract(Path(source), Path(t))
            reports = list(base.rglob("run_report.json"))
            report = json.loads(reports[0].read_text(encoding="utf-8")) if reports else {}

            for mp4 in sorted(base.rglob("shot_*.mp4")):
                sid = mp4.stem
                problem = video_problem(mp4)
                if sid not in shots:
                    print(f"SKIP {mp4.name}: not in storyboard")
                    continue
                if problem:
                    print(f"REJECT {mp4.name}: {problem}")
                    bad += 1
                    continue
                dest = shots_dir / mp4.name
                shutil.copyfile(mp4, dest)
                shot = shots[sid]
                key = cache.shot_key(
                    keyframe_path=cfg.output_dir / "keyframes" / f"{sid}.png",
                    motion_prompt=shot.get("motion_prompt", ""),
                    model_id=WAN_MODEL_ID,
                    generation_settings=shot.get("generation_settings", {}),
                )
                cache.put(stage="shots", cache_key=key, output_path=dest,
                          metadata={"shot_id": sid, "source": "kaggle", "report": report.get("shots", {}).get(sid)})
                m = report.get("shots", {}).get(sid, {})
                secs = m.get("seconds")
                logger.log(
                    stage="shots", provider="kaggle", model=WAN_MODEL_ID, status="SUCCESS", shot_id=sid,
                    output_paths=[str(dest)],
                    generation_parameters={**report.get("settings", {}), **{k: m[k] for k in m if k != "seconds"}},
                    seed=m.get("seed"),
                    # Only the generation time Kaggle measured; model load time is not included.
                    execution_duration_sec=secs,
                    gpu_minutes=round(secs / 60, 2) if secs else None,
                )
                print(f"OK     {mp4.name}  ({secs}s on {report.get('gpu', '?')})" if secs else f"OK     {mp4.name}")

            for wav in base.rglob("soundtrack.wav"):
                problem = audio_problem(wav)
                if problem:
                    print(f"REJECT soundtrack.wav: {problem}")
                    bad += 1
                    continue
                dest = music_dir / "soundtrack.wav"
                shutil.copyfile(wav, dest)
                mrep_files = list(base.rglob("music_report.json"))
                mrep = json.loads(mrep_files[0].read_text(encoding="utf-8")) if mrep_files else {}
                ms = sb.get("music_settings", {})
                key = cache.music_key(ms.get("prompt", ""), ms, MUSIC_MODEL_ID)
                cache.put(stage="music", cache_key=key, output_path=dest, metadata={"source": "kaggle", "report": mrep})
                total = (mrep.get("generate_seconds") or 0)
                logger.log(
                    stage="music", provider="kaggle", model=MUSIC_MODEL_ID, status="SUCCESS",
                    output_paths=[str(dest)], generation_parameters=mrep, seed=mrep.get("seed"),
                    execution_duration_sec=total or None,
                    gpu_minutes=round(total / 60, 2) if total else None,
                )
                print("OK     soundtrack.wav")

    print("\nNext: python -m pipeline.cli status && python -m pipeline.cli assemble")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pack")
    up = sub.add_parser("unpack")
    up.add_argument("sources", nargs="+")
    a = ap.parse_args()
    return pack() if a.cmd == "pack" else unpack(a.sources)


if __name__ == "__main__":
    sys.exit(main())
