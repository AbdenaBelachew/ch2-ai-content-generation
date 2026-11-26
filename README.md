# AI Heritage Short — Pipeline Foundation & Architecture

A reproducible, modular Python-based AI filmmaking pipeline designed to generate an authentic 60–90 second Ethiopian cultural heritage short film: **"ጣዕመ ትውፊት" (Taste of Heritage)**.

The short film tells the story of **Emaye Ayelech**, an original fictional Ethiopian grandmother, as she prepares a traditional coffee ceremony (*Buna*) in the highland morning light, sharing ancestral wisdom on patience, community, and cultural roots passed across generations.

---

## 1. Project Objective & Standards

- **Narration**: Authentic poetic Amharic narration in canonical Ge'ez Fidel script with timing and syllable pacing analysis.
- **Subtitles**: Synchronized English subtitles (SRT timecodes and video burn-in).
- **Soundtrack**: Original Ethiopian traditional acoustic soundtrack featuring indigenous instrumentation (*Masenqo*, *Washint*, *Krar*, *Kebero* at 68 BPM in the *Tizita* modal scale).
- **Radio Cut**: Scratch mix combining Amharic narration and acoustic music with sidechain ducking and loudness normalization before video rendering.
- **Character Consistency**: Dedicated character turnaround reference sheet generated with Cloudflare Workers AI FLUX to anchor cross-shot visual fidelity.
- **Video Diffusion**: High-fidelity moving shots rendered via Wan 2.2 TI2V-5B on Kaggle GPUs.
- **Audio Mixing**: Background music automatically ducked (-14 dB attenuation) beneath narration, normalized to EBU R128 (-16 LUFS, -1.5 dB true peak).
- **Dual Aspect Ratios**: Horizontal **16:9** (1920×1080) for cinematic display and vertical **9:16** (1080×1920) for mobile without stretching or distortion.
- **Ethical AI Disclosure**: Mandatory visible end card disclosing AI-orchestrated cultural preservation without copying any real person's likeness.

---

## 2. Technology & Provider Stack

All model identifiers and endpoints are centralized in `pipeline/config.py` and environment variables.

| Stage | Provider / Technology | Model / Tool | Role |
| :--- | :--- | :--- | :--- |
| **Story & Script** | Google Gemini API | `gemini-flash-latest` | Validation, translation fidelity, script refinement |
| **Amharic Narration** | Google Gemini TTS | `gemini-2.5-flash-preview-tts` | Authentic Amharic speech audio synthesis |
| **Character Sheet & Keyframes**| Cloudflare Workers AI | `@cf/black-forest-labs/flux-1-schnell` | Consistent character sheet & shot keyframes |
| **Moving Shots** | Kaggle GPU Notebooks | `Wan 2.2 TI2V-5B` | Video generation from keyframe + motion prompt |
| **Original Music** | Kaggle GPU Notebooks | `ACE-Step 1.5` | Traditional Ethiopian acoustic soundtrack |
| **Radio Cut & Assembly** | FFmpeg 7+ / Audio Synth | Native CLI / Python fallback | Radio cut, ducking, loudnorm, subtitles, end card, exports |

---

## 3. Repository Structure

```
ch2-ai-content-generation/
├── .env.example                     # Template for environment credentials
├── .gitignore                       # Git ignore rules for media, venv, and cache
├── Makefile                         # Unified CLI commands for workflow automation
├── requirements.txt                 # Pinned dependencies (jsonschema, pytest, requests, python-dotenv)
├── runs.jsonl                       # Append-only audit log for all model invocations
├── storyboard.json                  # Single source of truth storyboard (10 shots, 75s)
├── ARCHITECTURE.md                  # Comprehensive architectural design & data flow
├── DESIGN.md                        # Character profile, visual style & sound design
├── EXPERIMENTS.md                   # Experiment tracking framework and planned test backlog
├── FAILURES.md                      # Failure mode taxonomy, recovery rules, and resolved issues
├── COSTS.md                         # Unit economics, provider pricing & run budgets
├── ETHICS.md                        # Cultural representation, disclosure & AI ethics
├── README.md                        # Project documentation (this file)
├── schema/
│   └── storyboard.schema.json       # Draft 2020-12 JSON Schema contract for storyboard.json
├── kaggle/
│   ├── README.md                    # Instructions for running GPU workloads on Kaggle
│   ├── wan2_ti2v_notebook.ipynb     # Turnkey Jupyter notebook for Wan 2.2 video generation
│   ├── ace_step_music_notebook.ipynb# Turnkey Jupyter notebook for ACE-Step 1.5 music generation
│   ├── wan2_ti2v_runner.py          # Standalone runner script for Wan 2.2 TI2V-5B
│   └── ace_step_runner.py           # Standalone runner script for ACE-Step 1.5
├── outputs/                         # Destination for generated assets (.gitkeep preserved)
│   ├── keyframes/                   # Generated character sheet and shot keyframes (.png)
│   ├── shots/                       # Rendered Wan 2.2 MP4 video shots (.mp4)
│   ├── narration/                   # Amharic TTS audio files (.wav)
│   ├── music/                       # ACE-Step instrumental soundtrack (.wav)
│   ├── assembly/                    # Subtitles (.srt), end-card clips, and radio cut (.wav)
│   └── exports/                     # Master MP4 exports (film_9x16.mp4 and film_16x9.mp4)
├── pipeline/                        # Core Python package
│   ├── __init__.py
│   ├── cli.py                       # CLI entry point (validate, radio, keyframes, shots, etc.)
│   ├── config.py                    # Centralized settings & provider configs
│   ├── cache.py                     # Deterministic content-addressed cache manager
│   ├── logger.py                    # Honest audit logger for runs.jsonl
│   ├── validator.py                 # Storyboard schema and business rules validator
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract provider base with backoff retries
│   │   ├── cloudflare.py            # Cloudflare Workers AI FLUX provider & character sheet
│   │   ├── gemini.py                # Gemini script analysis, translation & TTS provider
│   │   └── kaggle.py                # Kaggle GPU payload prep & API runner
│   ├── stages/
│   │   ├── __init__.py
│   │   ├── script.py                # Stage 1: Storyboard & script validation, pacing analysis
│   │   ├── keyframes.py             # Stage 2: Character sheet & keyframe generation
│   │   ├── shots.py                 # Stage 3: Wan 2.2 video generation
│   │   ├── music.py                 # Stage 4: ACE-Step music soundtrack
│   │   ├── narration.py             # Stage 5: Amharic narration TTS
│   │   └── assembly.py              # Stage 6: FFmpeg video assembly & radio cut
│   └── utils/
│       ├── __init__.py
│       ├── ffmpeg.py                # FFmpeg command builder, ducking, SRT & fallback audio synth
│       └── hash.py                  # SHA-256 content hashing utilities
└── tests/                           # Comprehensive unit test suite (34 passed offline)
    ├── __init__.py
    ├── test_cache.py                # Caching, invalidation & isolation tests
    ├── test_cli.py                  # CLI command invocation, radio cut & pacing tests
    ├── test_ffmpeg.py               # FFmpeg filter construction, SRT & ducking tests
    ├── test_logger.py               # Runs logger schema & appending tests
    ├── test_schema.py               # JSON Schema validation tests
    └── test_validator.py            # Business logic validation tests
```

---

## 4. Quickstart: Installation & Commands

### Virtual Environment Setup
```bash
python -m venv .venv

# Activate environment:
# Windows: .\.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate

pip install -r requirements.txt
```

### Essential Workflow Commands
```bash
# 1. Pipeline Health & Provider Smoke Tests
make status
# or: python -m pipeline.cli status

# 2. Validate Storyboard Contract
make validate
# or: python -m pipeline.cli validate

# 3. Generate Character Turnaround Sheet
python -m pipeline.cli keyframes --character-sheet --mock

# 4. Generate Radio Cut Scratch Mix (Narration + Ducked Music)
make radio
# or: python -m pipeline.cli radio --mock

# 5. Generate Shot Keyframes
make keyframes
# or: python -m pipeline.cli keyframes --mock

# 6. Prepare Kaggle GPU Batch Manifests
make shots
make music

# 7. Run Full Pipeline Orchestration
make film
# or: python -m pipeline.cli film --mock --dry-run

# 8. Run All Unit Tests
make test
# or: pytest -v tests/
```

---

## 5. Kaggle GPU Execution Workflow

Heavy video diffusion (Wan 2.2 TI2V-5B) and music generation (ACE-Step 1.5) run on Kaggle GPUs:
1. `python -m pipeline.cli keyframes`, then `make kaggle-pack` builds `outputs/kaggle_bundle/` (upload as the Kaggle dataset `heritage-short-inputs`).
2. Run `kaggle/wan2_ti2v_notebook.ipynb` and `kaggle/ace_step_music_notebook.ipynb` on a Kaggle GPU (steps in [kaggle/README.md](kaggle/README.md)).
3. `python kaggle/bundle.py unpack outputs_shots.zip soundtrack_bundle.zip` validates and imports the results, then `python -m pipeline.cli assemble`.

---

## 6. Reproducibility & Caching Guarantee

- **Keyframes**: Cached using `SHA256(prompt + ref_image_hash + model_id + settings + seed)`.
- **Moving Shots**: Cached using `SHA256(keyframe_image_hash + motion_prompt + model_id + settings)`.
- **Narration**: Cached using `SHA256(amharic_text + voice_config + model_id)`.
- **Music**: Cached using `SHA256(music_prompt + settings + model_id)`.
- **Single Shot Regeneration**: Changing a prompt or seed in shot 4 invalidates only shot 4; all other 9 shots remain cached and untouched.

---

## 7. Audit Logging (`runs.jsonl`)

Every model invocation, cache hit, or failure is appended to `runs.jsonl` with:
- Exact ISO 8601 UTC timestamp
- Stage, Provider, and Model
- Shot ID where applicable
- Prompt and prompt hash
- Parameters, seeds, and file paths
- Measured execution duration
- Truthful status (`SUCCESS`, `FAILED`, `CACHED`) without fabricated metrics.

---

## Web UI (Studio)

A local web app: fill in a form, and the pipeline writes the storyboard (Gemini), paints the scenes
(Cloudflare FLUX), records Amharic narration (Gemini TTS), composes music, adds camera motion and
English captions, then renders 16:9 and/or 9:16 films you can play and download.

```powershell
.\.venv\Scripts\Activate.ps1
python -m web.server          # then open http://127.0.0.1:8000
```

- Inputs: title, story idea, main character, setting, length (8-12 shots), narration voice, music style, formats.
- Needs `GEMINI_API_KEY`, `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` in `.env`, and FFmpeg on PATH.
- Each film is built in its own folder under `web_jobs/` (git-ignored) with the standard pipeline commands.
- The server binds to localhost only; API keys stay on the server and are never sent to the browser.
- A film takes roughly 5-10 minutes; films are generated one at a time.
