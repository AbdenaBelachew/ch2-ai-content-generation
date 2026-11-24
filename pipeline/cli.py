"""Command Line Interface for AI Heritage Short Filmmaking Pipeline."""

import argparse
import json
from pathlib import Path
import sys
from typing import List, Optional

from pipeline.config import get_config
from pipeline.providers.cloudflare import CloudflareWorkersAIProvider
from pipeline.providers.gemini import GeminiProvider
from pipeline.providers.kaggle import KaggleProvider
from pipeline.stages.assembly import AssemblyStage
from pipeline.stages.keyframes import KeyframesStage
from pipeline.stages.music import MusicStage
from pipeline.stages.narration import NarrationStage
from pipeline.stages.script import ScriptStage
from pipeline.stages.shots import ShotsStage
from pipeline.utils.ffmpeg import is_ffmpeg_available
from pipeline.validator import load_json, validate_storyboard_file


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate storyboard against schema and business constraints."""
    print("=" * 60)
    print("AI Heritage Short - Storyboard Validation")
    print("=" * 60)
    storyboard_path = args.storyboard or get_config().storyboard_path
    print(f"Validating: {storyboard_path}")
    valid, errors = validate_storyboard_file(storyboard_path)
    if valid:
        print("[SUCCESS] Storyboard is 100% valid according to schema and rules.")
        return 0
    else:
        print(f"[FAILED] Storyboard validation found {len(errors)} error(s):")
        for idx, err in enumerate(errors, 1):
            print(f"  {idx}. {err}")
        return 1


def cmd_script(args: argparse.Namespace) -> int:
    """Execute script and narrative validation/refinement."""
    print("=" * 60)
    print("AI Heritage Short - Script Stage")
    print("=" * 60)
    stage = ScriptStage()
    try:
        storyboard = stage.run(refine=args.refine, storyboard_path=args.storyboard)
        print(f"Title: {storyboard.get('film_title')}")
        print(f"Target duration: {storyboard.get('project_metadata', {}).get('target_total_duration')}s")
        print(f"Total shots: {len(storyboard.get('shots', []))}")
        print("[SUCCESS] Script stage completed.")
        return 0
    except Exception as exc:
        print(f"[ERROR] Script stage failed: {exc}")
        return 1


def cmd_keyframes(args: argparse.Namespace) -> int:
    """Generate or retrieve keyframes using FLUX."""
    print("=" * 60)
    print("AI Heritage Short - Keyframes Generation")
    print("=" * 60)
    stage = KeyframesStage(mock_if_unconfigured=args.mock)
    try:
        if getattr(args, "character_sheet", False):
            sheets = stage.generate_character_sheets(
                storyboard_path=args.storyboard,
                force_regenerate=args.force,
            )
            print(f"[SUCCESS] Processed {len(sheets)} character sheet(s):")
            for cid, path in sheets.items():
                print(f"  - Character {cid}: {path}")
            return 0

        results = stage.run(
            storyboard_path=args.storyboard,
            force_regenerate=args.force,
            shot_ids=args.shots,
        )
        print(f"[SUCCESS] Processed {len(results)} keyframe(s):")
        for shot_id, path in results.items():
            print(f"  - {shot_id}: {path}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Keyframes stage failed: {exc}")
        return 1


def cmd_shots(args: argparse.Namespace) -> int:
    """Prepare or generate Wan 2.2 TI2V-5B video clips."""
    print("=" * 60)
    print("AI Heritage Short - Moving Shots Generation (Wan 2.2 TI2V-5B)")
    print("=" * 60)
    stage = ShotsStage(mock_if_unconfigured=args.mock)
    try:
        res = stage.run(
            storyboard_path=args.storyboard,
            force_regenerate=args.force,
            shot_ids=args.shots,
        )
        status = res.get("status")
        print(f"Status: {status}")
        if status == "ALL_CACHED":
            print("[SUCCESS] All shots are up-to-date and cached.")
        elif status == "COMPLETED_MOCK":
            print("[SUCCESS] Generated mock shots for testing.")
        elif status == "REQUIRES_KAGGLE_GPU":
            print(f"[ACTION REQUIRED] {res.get('message')}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Shots stage failed: {exc}")
        return 1


def cmd_narration(args: argparse.Namespace) -> int:
    """Generate Amharic speech audio with Gemini TTS."""
    print("=" * 60)
    print("AI Heritage Short - Amharic Narration Generation")
    print("=" * 60)
    stage = NarrationStage(mock_if_unconfigured=args.mock)
    try:
        results = stage.run(
            storyboard_path=args.storyboard,
            force_regenerate=args.force,
            shot_ids=args.shots,
        )
        print(f"[SUCCESS] Processed narration for {len(results)} shot(s).")
        return 0
    except Exception as exc:
        print(f"[ERROR] Narration stage failed: {exc}")
        return 1


def cmd_radio(args: argparse.Namespace) -> int:
    """Generate Amharic narration, music, and mix into a Radio Cut scratch track."""
    print("=" * 60)
    print("AI Heritage Short - Radio Cut Scratch Track")
    print("=" * 60)
    # Ensure narration and music exist (using mock fallback if unconfigured or requested)
    narr_stage = NarrationStage(mock_if_unconfigured=args.mock)
    narr_stage.run(storyboard_path=args.storyboard, force_regenerate=args.force)

    music_stage = MusicStage(mock_if_unconfigured=args.mock)
    music_stage.run(storyboard_path=args.storyboard, force_regenerate=args.force)

    assembly_stage = AssemblyStage(dry_run=args.dry_run)
    res = assembly_stage.assemble_radio_cut(storyboard_path=args.storyboard)
    print(f"Radio Cut Status: {res.get('status')}")
    if "radio_cut_path" in res:
        print(f"[SUCCESS] Radio Cut ready at: {res['radio_cut_path']}")
    return 0


def cmd_music(args: argparse.Namespace) -> int:
    """Generate or prepare soundtrack with ACE-Step 1.5."""
    print("=" * 60)
    print("AI Heritage Short - Original Soundtrack (ACE-Step 1.5)")
    print("=" * 60)
    stage = MusicStage(mock_if_unconfigured=args.mock)
    try:
        res = stage.run(
            storyboard_path=args.storyboard,
            force_regenerate=args.force,
        )
        print(f"Status: {res.get('status')}")
        if "soundtrack_path" in res:
            print(f"Soundtrack: {res['soundtrack_path']}")
        if "message" in res:
            print(f"[ACTION REQUIRED] {res['message']}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Music stage failed: {exc}")
        return 1


def cmd_assemble(args: argparse.Namespace) -> int:
    """Assemble final video exports via FFmpeg."""
    print("=" * 60)
    print("AI Heritage Short - Final Video Assembly")
    print("=" * 60)
    stage = AssemblyStage(dry_run=args.dry_run)
    try:
        res = stage.run(
            storyboard_path=args.storyboard,
            aspect_ratios=args.aspect_ratios,
        )
        print(f"Subtitles: {res.get('subtitles_srt')}")
        missing = res.get("missing_inputs", {})
        if missing.get("shots") or missing.get("narration") or missing.get("music"):
            print("[INFO] Assembly prerequisites missing:")
            if missing.get("shots"):
                print(f"  Missing shots: {', '.join(missing['shots'])}")
            if missing.get("narration"):
                print("  Missing full narration audio (outputs/narration/full_narration.wav)")
            if missing.get("music"):
                print("  Missing soundtrack audio (outputs/music/soundtrack.wav)")
        else:
            print("[SUCCESS] All input assets present.")
        for aspect, exp in res.get("exports", {}).items():
            print(f"  Export ({aspect}): {exp}")
        return 0
    except Exception as exc:
        print(f"[ERROR] Assembly failed: {exc}")
        return 1


def cmd_film(args: argparse.Namespace) -> int:
    """Run full orchestration pipeline."""
    print("=" * 60)
    print("AI Heritage Short - Full Film Orchestrator")
    print("=" * 60)

    # 1. Validation & Script
    print("\n--- [1/6] Validating Storyboard & Script ---")
    script_stage = ScriptStage()
    try:
        storyboard = script_stage.run(storyboard_path=args.storyboard)
        print(f"Loaded '{storyboard.get('film_title')}' with {len(storyboard.get('shots', []))} shots.")
    except Exception as exc:
        print(f"[FATAL] Storyboard validation failed: {exc}")
        return 1

    # 2. Keyframes
    print("\n--- [2/6] Keyframe Generation ---")
    kf_stage = KeyframesStage(mock_if_unconfigured=args.mock)
    try:
        kf_results = kf_stage.run(storyboard_path=args.storyboard, force_regenerate=args.force)
        print(f"Keyframes ready: {len(kf_results)} files.")
    except Exception as exc:
        print(f"[ERROR] Keyframes generation halted: {exc}")

    # 3. Narration
    print("\n--- [3/6] Amharic Narration Generation ---")
    narr_stage = NarrationStage(mock_if_unconfigured=args.mock)
    try:
        narr_results = narr_stage.run(storyboard_path=args.storyboard, force_regenerate=args.force)
        print(f"Narration ready: {len(narr_results)} files.")
    except Exception as exc:
        print(f"[ERROR] Narration generation halted: {exc}")

    # 4. Moving Shots (Kaggle Wan 2.2)
    print("\n--- [4/6] Moving-Shot Generation (Wan 2.2 TI2V-5B) ---")
    shots_stage = ShotsStage(mock_if_unconfigured=args.mock)
    try:
        shots_res = shots_stage.run(storyboard_path=args.storyboard, force_regenerate=args.force)
        print(f"Shots status: {shots_res.get('status')}")
        if shots_res.get("status") == "REQUIRES_KAGGLE_GPU":
            print(f"[NOTE] {shots_res.get('message')}")
    except Exception as exc:
        print(f"[ERROR] Shots generation halted: {exc}")

    # 5. Music Generation (Kaggle ACE-Step 1.5)
    print("\n--- [5/6] Music Generation (ACE-Step 1.5) ---")
    music_stage = MusicStage(mock_if_unconfigured=args.mock)
    try:
        music_res = music_stage.run(storyboard_path=args.storyboard, force_regenerate=args.force)
        print(f"Music status: {music_res.get('status')}")
        if music_res.get("status") == "REQUIRES_KAGGLE_GPU":
            print(f"[NOTE] {music_res.get('message')}")
    except Exception as exc:
        print(f"[ERROR] Music generation halted: {exc}")

    # 6. Assembly
    print("\n--- [6/6] Final Video Assembly ---")
    assembly_stage = AssemblyStage(dry_run=args.dry_run)
    try:
        assembly_res = assembly_stage.run(storyboard_path=args.storyboard)
        for aspect, exp in assembly_res.get("exports", {}).items():
            print(f"Export ({aspect}): {exp}")
    except Exception as exc:
        print(f"[ERROR] Final assembly halted: {exc}")

    print("\nFull orchestration step complete.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Print comprehensive pipeline, provider, and asset status."""
    print("=" * 60)
    print("AI Heritage Short - Pipeline Status & Health Check")
    print("=" * 60)

    cfg = get_config()

    # 1. Storyboard check
    storyboard_path = cfg.storyboard_path
    valid, errors = validate_storyboard_file(storyboard_path)
    print(f"\n[Storyboard]: {storyboard_path.name}")
    print(f"  Valid: {'YES' if valid else 'NO'}")
    if not valid:
        for err in errors[:3]:
            print(f"    - {err}")

    # 2. Providers Smoke Tests
    print("\n[External Providers Smoke Tests]:")
    gemini = GeminiProvider().verify_connection()
    print(f"  Gemini API: {gemini.get('status')} - {gemini.get('message')}")

    cloudflare = CloudflareWorkersAIProvider().verify_connection()
    print(f"  Cloudflare Workers AI: {cloudflare.get('status')} - {cloudflare.get('message')}")

    kaggle = KaggleProvider().verify_connection()
    print(f"  Kaggle API: {kaggle.get('status')} - {kaggle.get('message')}")

    ffmpeg_ok = is_ffmpeg_available()
    print(f"  FFmpeg Binary: {'FOUND' if ffmpeg_ok else 'NOT FOUND IN PATH'}")

    # 3. Asset Counts
    shots_count = 10
    if valid and storyboard_path.is_file():
        sb_data = load_json(storyboard_path)
        shots_count = len(sb_data.get("shots", []))

    kf_dir = cfg.output_dir / "keyframes"
    existing_kfs = list(kf_dir.glob("*.png")) if kf_dir.exists() else []

    shots_dir = cfg.output_dir / "shots"
    existing_shots = list(shots_dir.glob("*.mp4")) if shots_dir.exists() else []

    narr_dir = cfg.output_dir / "narration"
    existing_narr = list(narr_dir.glob("shot_*.wav")) if narr_dir.exists() else []

    music_file = cfg.output_dir / "music" / "soundtrack.wav"
    music_ok = music_file.exists()

    exports_dir = cfg.output_dir / "exports"
    exp_9x16 = (exports_dir / "film_9x16.mp4").exists()
    exp_16x9 = (exports_dir / "film_16x9.mp4").exists()

    print("\n[Generated Assets Progress]:")
    print(f"  Keyframes: {len(existing_kfs)} / {shots_count} shots generated")
    print(f"  Video Shots: {len(existing_shots)} / {shots_count} shots generated")
    print(f"  Narration: {len(existing_narr)} / {shots_count} shots generated")
    print(f"  Soundtrack: {'READY' if music_ok else 'PENDING'}")
    print(f"  Export 9:16: {'READY' if exp_9x16 else 'PENDING'}")
    print(f"  Export 16:9: {'READY' if exp_16x9 else 'PENDING'}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pipeline",
        description="AI Heritage Short Filmmaking Pipeline CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate storyboard.json")
    p_val.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_val.set_defaults(func=cmd_validate)

    # script
    p_scr = subparsers.add_parser("script", help="Validate/refine script")
    p_scr.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_scr.add_argument("--refine", action="store_true", help="Call Gemini to refine text")
    p_scr.set_defaults(func=cmd_script)

    # keyframes
    p_kf = subparsers.add_parser("keyframes", help="Generate keyframes via Cloudflare FLUX")
    p_kf.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_kf.add_argument("--force", action="store_true", help="Force regenerate keyframes")
    p_kf.add_argument("--mock", action="store_true", help="Generate offline mock images")
    p_kf.add_argument("--character-sheet", action="store_true", help="Generate character reference sheet")
    p_kf.add_argument("--shots", nargs="+", help="Specific shot IDs to generate")
    p_kf.set_defaults(func=cmd_keyframes)

    # shots
    p_sh = subparsers.add_parser("shots", help="Generate moving shots via Wan 2.2 on Kaggle")
    p_sh.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_sh.add_argument("--force", action="store_true", help="Force regenerate shots")
    p_sh.add_argument("--mock", action="store_true", help="Generate offline mock video")
    p_sh.add_argument("--shots", nargs="+", help="Specific shot IDs to generate")
    p_sh.set_defaults(func=cmd_shots)

    # narration
    p_narr = subparsers.add_parser("narration", help="Generate Amharic TTS narration")
    p_narr.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_narr.add_argument("--force", action="store_true", help="Force regenerate narration")
    p_narr.add_argument("--mock", action="store_true", help="Generate offline mock audio")
    p_narr.add_argument("--shots", nargs="+", help="Specific shot IDs to generate")
    p_narr.set_defaults(func=cmd_narration)

    # music
    p_mus = subparsers.add_parser("music", help="Generate soundtrack via ACE-Step on Kaggle")
    p_mus.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_mus.add_argument("--force", action="store_true", help="Force regenerate music")
    p_mus.add_argument("--mock", action="store_true", help="Generate offline mock audio")
    p_mus.set_defaults(func=cmd_music)

    # radio
    p_rad = subparsers.add_parser("radio", help="Generate Radio Cut scratch mix (narration + ducked music)")
    p_rad.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_rad.add_argument("--force", action="store_true", help="Force regenerate audio tracks")
    p_rad.add_argument("--mock", action="store_true", help="Generate offline mock audio if unconfigured")
    p_rad.add_argument("--dry-run", action="store_true", help="Do not write mixed audio")
    p_rad.set_defaults(func=cmd_radio)

    # assemble
    p_ass = subparsers.add_parser("assemble", help="Assemble final video exports via FFmpeg")
    p_ass.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_ass.add_argument("--dry-run", action="store_true", help="Build commands without executing")
    p_ass.add_argument("--aspect-ratios", nargs="+", help="Aspect ratios to export, e.g. 9:16 16:9")
    p_ass.set_defaults(func=cmd_assemble)

    # film
    p_flm = subparsers.add_parser("film", help="Run full pipeline end-to-end")
    p_flm.add_argument("--storyboard", type=str, help="Path to storyboard JSON")
    p_flm.add_argument("--force", action="store_true", help="Force regenerate all assets")
    p_flm.add_argument("--mock", action="store_true", help="Mock unconfigured providers")
    p_flm.add_argument("--dry-run", action="store_true", help="Dry run final assembly")
    p_flm.set_defaults(func=cmd_film)

    # status
    p_st = subparsers.add_parser("status", help="Display pipeline health and assets status")
    p_st.set_defaults(func=cmd_status)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()

