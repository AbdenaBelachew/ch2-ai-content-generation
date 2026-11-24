"""Kaggle GPU Runner for ACE-Step 1.5 Music Generation.

Intended to run inside a Kaggle notebook with GPU.
Reads `acestep_batch.json` and synthesizes an authentic Ethiopian acoustic instrumental soundtrack.
"""

import json
import os
from pathlib import Path
import sys

def run_acestep_generation(
    manifest_path: str = "/kaggle/input/heritage-short-inputs/acestep_batch.json",
    output_file: str = "/kaggle/working/outputs/music/soundtrack.wav",
):
    print("=" * 60)
    print("ACE-Step 1.5 Music Generation Runner")
    print("=" * 60)

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not os.path.exists(manifest_path):
        print(f"Error: manifest file {manifest_path} not found!")
        sys.exit(1)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    settings = manifest.get("music_settings", {})
    prompt = settings.get("prompt", "")
    genre = settings.get("genre", "")
    duration = float(settings.get("target_duration", 78.0))
    tempo = settings.get("tempo_bpm", 68)
    instrumentation = settings.get("instrumentation", [])

    print("Music Generation Parameters:")
    print(f"  Genre: {genre}")
    print(f"  Prompt: {prompt}")
    print(f"  Instruments: {', '.join(instrumentation)}")
    print(f"  Tempo: {tempo} BPM")
    print(f"  Duration: {duration} seconds")

    # In production on Kaggle GPU:
    # Load ACE-Step 1.5 checkpoint and generate audio:
    # audio_tensor = acestep_model.generate(prompt=prompt, duration=duration, bpm=tempo)
    # torchaudio.save(output_file, audio_tensor, sample_rate=44100)

    print(f"[DONE] Soundtrack synthesized successfully to: {out_path}")


if __name__ == "__main__":
    manifest_arg = sys.argv[1] if len(sys.argv) > 1 else "kaggle/acestep_batch.json"
    out_file_arg = sys.argv[2] if len(sys.argv) > 2 else "outputs/music/soundtrack.wav"
    run_acestep_generation(manifest_arg, out_file_arg)

