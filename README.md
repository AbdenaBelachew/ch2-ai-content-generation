# AI Heritage Short — Pipeline Foundation

A reproducible Python-based AI filmmaking pipeline designed to generate an authentic 60–90 second Ethiopian cultural heritage short film: **"ጣዕመ ትውፊት" (Taste of Heritage)**.

The short film tells the story of **Emaye Ayelech**, a fictional Ethiopian grandmother, as she prepares a traditional coffee ceremony (*Buna*) in the highland dawn light, sharing ancestral wisdom on patience, community, and cultural roots.

---

## 1. Film Specifications & Requirements

- **Narrative**: An intimate 10-shot visual poem (~75 seconds) celebrating Ethiopian coffee culture and maternal wisdom.
- **Narration**: Authentic Amharic narration in Ge'ez Fidel script.
- **Subtitles**: Synchronized English subtitles (SRT and video burn-in).
- **Soundtrack**: Original Ethiopian traditional acoustic soundtrack (Masenqo, Washint flute, Krar plucking, Kebero drum).
- **Audio Mixing**: Background music automatically ducked beneath speech via sidechain compression, normalized to EBU R128 standards.
- **End Card**: Visible AI-generated-content disclosure end card honoring cultural preservation.
- **Dual Aspect Ratios**: Both vertical **9:16** (1080×1920) for mobile/socials and horizontal **16:9** (1920×1080) for cinematic viewing without stretching or distortion.
- **Character Consistency**: Fictional AI character profile maintained deterministically across shots.

---

## 2. Technology & Provider Stack

The pipeline avoids hardcoding model identifiers or API endpoints, centralizing all configurations in `pipeline/config.py` and environment variables.

| Stage | Provider / Technology | Model / Tool | Role |
| :--- | :--- | :--- | :--- |
| **Story & Script** | Google Gemini API | `gemini-2.5-flash` | Story validation, translation, script refinement |
| **Amharic Narration** | Google Gemini TTS | `gemini-2.5-flash-tts` | Authentic Amharic speech audio synthesis |
| **Visual Keyframes** | Cloudflare Workers AI | `@cf/black-forest-labs/flux-1-schnell` | Consistent photorealistic visual keyframes |
| **Moving Shots** | Kaggle GPU Notebooks | `Wan 2.2 TI2V-5B` | Video generation from keyframe + motion prompt |
| **Original Music** | Kaggle GPU Notebooks | `ACE-Step 1.5` | Traditional Ethiopian acoustic instrumental music |
| **Assembly & Master** | FFmpeg 7+ | Native CLI filter complex | Concat, ducking, loudnorm, subtitles, end card, exports |

---

## 3. Repository Structure

```
ch2-ai-content-generation/
├── .env.example                     # Template for environment credentials
├── .gitignore                       # Git ignore rules for media and cache
├── ARCHITECTURE.md                  # Detailed architectural design & data flow
├── DESIGN.md                        # Character profile, visual style & sound design
├── EXPERIMENTS.md                   # Experiment tracking framework and template
├── FAILURES.md                      # Failure mode taxonomy & recovery protocols
├── COSTS.md                         # Unit economics, provider pricing & run budgets
├── ETHICS.md                        # Cultural representation, disclosure & AI ethics
├── Makefile                         # Unified CLI commands for workflow automation
├── README.md                        # Project documentation (this file)
├── requirements.txt                 # Python dependencies
├── runs.jsonl                       # Append-only audit log for all model invocations
├── storyboard.json                  # Single source of truth storyboard (10 shots, 75s)
├── kaggle/                          # Kaggle GPU execution files & runners
│   ├── README.md                    # Instructions for running GPU workloads on Kaggle
│   ├── wan2_ti2v_runner.py          # Runner script for Wan 2.2 TI2V-5B video generation
│   └── ace_step_runner.py           # Runner script for ACE-Step 1.5 music generation
├── outputs/                         # Destination for generated assets
│   ├── keyframes/                   # Generated FLUX PNG keyframes
│   ├── shots/                       # Rendered Wan 2.2 MP4 video shots
│   ├── narration/                   # Amharic TTS audio files (.wav)
│   ├── music/                       # ACE-Step instrumental soundtrack (.wav)
│   ├── assembly/                    # Subtitles (.srt) and end-card clips
│   └── exports/                     # Final master MP4 exports (9:16 and 16:9)
├── pipeline/                        # Core Python package
│   ├── __init__.py
│   ├── cli.py                       # CLI entry point (validate, keyframes, shots, etc.)
│   ├── config.py                    # Centralized settings & provider configs
│   ├── cache.py                     # Deterministic content-addressed cache manager
│   ├── logger.py                    # Honest audit logger for runs.jsonl
│   ├── validator.py                 # Storyboard schema and business rules validator
│   ├── providers/                   # External API & runner abstractions
│   │   ├── __init__.py
│   │   ├── base.py                  # Abstract provider base with backoff retries
│   │   ├── cloudflare.py            # Cloudflare Workers AI FLUX provider
│   │   ├── gemini.py                # Gemini story refinement & TTS provider
│   │   └── kaggle.py                # Kaggle GPU payload prep & API runner
│   ├── stages/                      # Pipeline stage implementations
│   │   ├── __init__.py
│   │   ├── script.py                # Stage 1: Storyboard & script validation
│   │   ├── keyframes.py             # Stage 2: Keyframe generation
│   │   ├── shots.py                 # Stage 3: Wan 2.2 video generation
│   │   ├── music.py                 # Stage 4: ACE-Step music soundtrack
│   │   ├── narration.py             # Stage 5: Amharic narration TTS
│   │   └── assembly.py              # Stage 6: FFmpeg video assembly
│   └── utils/
│       ├── __init__.py
│       ├── ffmpeg.py                # FFmpeg command builder, ducking & SRT utils
│       └── hash.py                  # SHA-256 content hashing utilities
├── schema/
│   └── storyboard.schema.json       # JSON Schema contract for storyboard.json
└── tests/                           # Comprehensive unit test suite
    ├── __init__.py
    ├── test_cache.py                # Caching, invalidation & isolation tests
    ├── test_cli.py                  # CLI command invocation tests
    ├── test_ffmpeg.py               # FFmpeg filter construction tests
    ├── test_logger.py               # Runs logger schema & appending tests
    ├── test_schema.py               # JSON Schema validation tests
    └── test_validator.py            # Business logic validation tests
```

---

## 4. Installation & Setup

### Prerequisites
- Python 3.11 or newer (tested with Python 3.13)
- FFmpeg 6.0+ installed and available in PATH (or specified via `FFMPEG_PATH`)

### Setup Virtual Environment
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` to supply credentials when performing live provider calls:
- `GEMINI_API_KEY`: API key from Google AI Studio.
- `CLOUDFLARE_ACCOUNT_ID` & `CLOUDFLARE_API_TOKEN`: Cloudflare Workers AI credentials.
- `KAGGLE_USERNAME` & `KAGGLE_KEY`: Kaggle credentials (optional; manual fallback provided).

---

## 5. Commands & Workflow

All commands can be invoked via the `Makefile` or `python -m pipeline.cli`:

### Pipeline Health & Provider Smoke Test
```bash
make status
# or: python -m pipeline.cli status
```
*Performs minimal smoke tests verifying whether credentials are configured and endpoints are accessible, without pretending success when unconfigured.*

### Storyboard Validation
```bash
make validate
# or: python -m pipeline.cli validate
```
*Validates `storyboard.json` against `schema/storyboard.schema.json` and checks shot counts, duplicate IDs, duration totals, and character references.*

### Radio Play Scratch Track
```bash
make radio
```
*Generates the Amharic narration audio and music soundtrack, testing pacing and emotional flow prior to video generation.*

### Individual Stage Commands
```bash
# Keyframe generation
python -m pipeline.cli keyframes [--shots shot_01 shot_02] [--force] [--mock]

# Moving shots preparation
python -m pipeline.cli shots [--mock]

# Amharic narration generation
python -m pipeline.cli narration [--mock]

# Soundtrack generation
python -m pipeline.cli music [--mock]

# Final assembly (dry-run to inspect FFmpeg command)
python -m pipeline.cli assemble --dry-run
```

### Full Film Orchestration
```bash
make film
# or: python -m pipeline.cli film
```
*Executes all stages in sequence, reusing cached outputs, logging each run to `runs.jsonl`, and clearly reporting pending Kaggle GPU tasks.*

### Running Tests
```bash
make test
# or: pytest -v tests/
```

---

## 6. Kaggle GPU Orchestration

Because video generation (Wan 2.2 TI2V-5B) and music generation (ACE-Step 1.5) require GPU acceleration, Kaggle GPU notebooks (T4 or P100) are utilized:

1. Running `python -m pipeline.cli shots` produces `kaggle/wan_batch.json`.
2. Running `python -m pipeline.cli music` produces `kaggle/acestep_batch.json`.
3. Follow [kaggle/README.md](file:///d:/tenx/challenges/ch2-ai-content-generation/kaggle/README.md) to execute the batch on Kaggle.
4. Place output files in `outputs/shots/` and `outputs/music/soundtrack.wav`.
5. Run `python -m pipeline.cli assemble` to produce final MP4 exports.

---

## 7. Caching & Reproducibility Guarantee

The pipeline features a content-addressed caching engine (`pipeline/cache.py`):
- **Keyframes**: Cached using `SHA256(prompt + ref_image_hash + model_id + settings + seed)`.
- **Moving Shots**: Cached using `SHA256(keyframe_image_hash + motion_prompt + model_id + settings)`.
- **Narration**: Cached using `SHA256(amharic_text + voice_config + model_id)`.
- **Music**: Cached using `SHA256(music_prompt + settings + model_id)`.

**Granular Invalidation**: If you modify the prompt or seed for `shot_03`, only `shot_03` keyframe and video clip are regenerated. All other 9 shots remain cached and untouched.

---

## 8. Audit Logging (`runs.jsonl`)

Every model invocation, cache hit, or failure is appended to `runs.jsonl` with:
- Exact UTC timestamp
- Stage, Provider, and Model
- Shot ID (where applicable)
- Prompt or prompt hash
- Generation parameters and seed
- Input and output file paths
- Measured execution duration
- Actual cost / GPU minutes (never fabricated or guessed)
- Status (`SUCCESS`, `FAILED`, `CACHED`)
- Complete error diagnostics upon failure

---

## 9. Troubleshooting

- **`storyboard.json validation failed`**: Run `python -m pipeline.cli validate` to view specific field-level schema or business rule errors.
- **`Provider UNCONFIGURED`**: Verify that `.env` contains valid credentials and run `python -m pipeline.cli status`.
- **`FFmpeg not found`**: Ensure FFmpeg is installed and added to your system PATH, or specify `FFMPEG_PATH=/path/to/ffmpeg` in `.env`.

