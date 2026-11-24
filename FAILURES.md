# AI Heritage Short — Failure Analysis & Mitigation Taxonomy

This document catalogs potential failure modes across the AI filmmaking pipeline, establishes automated recovery mechanisms, and documents real technical issues encountered and resolved during foundation engineering.

---

## 1. Failure Modes & Mitigations Taxonomy

### 1.1 Keyframe Generation (Cloudflare Workers AI / FLUX)
| Failure Mode | Root Cause | Pipeline Mitigation |
| :--- | :--- | :--- |
| **Facial & Costume Drift** | Random diffusion seeds across shots | Reusable character traits in prompt; fixed seeds (`generation_settings.seed`); granular single-shot re-renders. |
| **Anatomical Warping** | Complex hand poses during coffee washing | Macro framing, detailed positive prompts, explicit negative prompts (`deformed hands, distorted anatomy`). |
| **Rate Limits (HTTP 429)** | Exceeding Cloudflare Workers AI burst limits | `retry_with_backoff` with exponential delays (1s, 2s, 4s); persistent caching prevents redundant calls. |
| **Authentication Errors (401/403)** | Expired or incorrect `CLOUDFLARE_API_TOKEN` | Immediately marked non-retryable (`AuthenticationError`) to avoid infinite loops and unnecessary billable hits. |

### 1.2 Moving-Shot Video Generation (Wan 2.2 TI2V-5B on Kaggle)
| Failure Mode | Root Cause | Pipeline Mitigation |
| :--- | :--- | :--- |
| **GPU Out of Memory (OOM)** | Wan 2.2 model size exceeds 16GB VRAM on T4 | Model offloading / CPU offload enabled in `wan2_ti2v_runner.py`; sequential shot generation. |
| **Temporal Flickering** | Aggressive motion prompts between frames | Restrict motion prompts to subtle camera movement and natural smoke/water dynamics; anchor to source keyframe. |
| **Missing Output Files** | Kaggle job interruption | Pipeline checks output presence before assembly; marks status as `REQUIRES_KAGGLE_GPU` without pretending success. |

### 1.3 Amharic Narration & Audio
| Failure Mode | Root Cause | Pipeline Mitigation |
| :--- | :--- | :--- |
| **Phonetic Mispronunciation** | Model interpreting Ge'ez script incorrectly | Canonical Fidel text verification; previewing via `make radio` before video assembly. |
| **Audio Clipping / Masking** | Music overpowering soft speech | Automatic FFmpeg sidechain ducking filter (`sidechaincompress` at -14 dB attenuation) and EBU R128 loudness normalization. |

### 1.4 Video Assembly & Export (FFmpeg)
| Failure Mode | Root Cause | Pipeline Mitigation |
| :--- | :--- | :--- |
| **Aspect Ratio Distortion** | Naive stretching from 16:9 to 9:16 | Custom FFmpeg filter complex using `force_original_aspect_ratio=increase` followed by center cropping (`crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2`). |
| **Subtitle Desynchronization** | Drift in cumulative shot durations | Dynamic SRT generator calculates timecodes directly from individual shot `duration` fields in `storyboard.json`. |

---

## 2. Issues Encountered & Resolved During Foundation Setup

1. **Python Executable Discovery on Windows**:
   - *Issue*: Direct invocation of `python` in PowerShell sandbox failed because Python was installed in user local AppData without system PATH inclusion.
   - *Resolution*: Identified Python 3.13 at `C:\Users\abdio\AppData\Local\Programs\Python\Python313\python.exe` and initialized an isolated workspace virtual environment at `.venv`.
2. **Pip Network Access Under Sandbox**:
   - *Issue*: Default terminal sandbox restricts outbound internet access, causing `pip install` to fail DNS resolution for `pypi.org`.
   - *Resolution*: Executed `pip install` with unsandboxed elevation (`BypassSandbox: true`) specifically for package acquisition, keeping all subsequent file generation, compilation, and testing safely inside the sandbox.
3. **Typing Import Omission in Validator**:
   - *Issue*: `Optional` was used in `pipeline/validator.py` type hints without import from `typing`.
   - *Resolution*: Added `Optional` to imports and verified with smoke tests.

