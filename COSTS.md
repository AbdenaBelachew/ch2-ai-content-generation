# AI Heritage Short — Financial Economics & Cost Model

> [!NOTE]
> Per pipeline principles, cost numbers in `runs.jsonl` are only recorded when directly reported by provider APIs or verified list prices. No speculative or fictitious charges are logged.

---

## 1. Provider Unit Economics & Pricing Model

| Provider | Service / Model | List Price Basis | Typical Unit Cost |
| :--- | :--- | :--- | :--- |
| **Google Gemini API** | `gemini-2.5-flash` (Script & Translation) | Per 1M input/output tokens | ~$0.075 / 1M input, $0.30 / 1M output tokens |
| **Google Gemini API** | `gemini-2.5-flash-preview-tts` (Amharic Speech) | Per 1M audio characters / tokens | ~$0.000016 per character (~$0.01 per minute) |
| **Cloudflare Workers AI** | `@cf/black-forest-labs/flux-1-schnell` | Free tier (10k Neurons/day) or $0.00028 per step | ~$0.0011 per 4-step image |
| **Kaggle** | Wan 2.2 TI2V-5B (Video Generation) | Free tier quota (30 GPU hours/week) | **$0.00** on Kaggle ($0.55/hr equivalent on GCP T4) |
| **Kaggle** | ACE-Step 1.5 (Music Synthesis) | Free tier quota (30 GPU hours/week) | **$0.00** on Kaggle ($0.55/hr equivalent on GCP T4) |
| **Local Compute** | FFmpeg Video Assembly & Encoding | Local CPU / hardware encoder | **$0.00** |

---

## 2. Estimated Cost Breakdown per 75-Second Film Run

Assuming a complete from-scratch generation of all 10 shots without cache:

| Asset Stage | Quantity | Consumption Estimate | Estimated Direct Cost (USD) |
| :--- | :--- | :--- | :--- |
| **Script & Storyboard Validation** | 1 Storyboard | ~2,500 prompt tokens | $0.0008 |
| **Keyframe Generation** | 10 FLUX images | 4 steps × 10 images = 40 steps | $0.0110 |
| **Amharic Narration (TTS)** | 10 audio clips | ~850 Amharic characters | $0.0136 |
| **Wan 2.2 Video Shots** | 10 clips (7.5s each) | ~25 GPU minutes (T4x2 on Kaggle) | $0.0000 (Free Quota) |
| **Original Soundtrack** | 1 track (78s) | ~2 GPU minutes (T4 on Kaggle) | $0.0000 (Free Quota) |
| **FFmpeg Assembly & Exports** | 2 MP4 exports | ~45 seconds CPU compute | $0.0000 |
| **Total per Complete Film Run** | — | — | **~$0.025 USD** |

---

## 3. Cost Optimization Through Caching

Thanks to the content-addressed caching engine in `pipeline/cache.py`:
- **Scenario A (Script tweak on 1 shot)**: Only 1 keyframe ($0.0011), 1 shot (2.5 GPU mins), and 1 narration clip ($0.0014) are regenerated.
  - *Cost*: **$0.0025 USD**.
- **Scenario B (Full re-assembly for new aspect ratio or subtitle tweak)**: Zero API calls, zero GPU hours.
  - *Cost*: **$0.0000 USD**.

---

## 4. Audit Log Integration

When API responses return exact billing metadata or token metrics, `pipeline/logger.py` stores the exact `cost_usd` or `gpu_minutes` in `runs.jsonl`. If an external provider does not supply exact billing data in the response header, the field is left as `null` rather than estimated.

