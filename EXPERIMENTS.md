# AI Heritage Short — Experiments Log & Evaluation Framework

> [!NOTE]
> Per project guidelines, no experimental outcomes, viewer metrics, or audience feedback have been fabricated. This document establishes the scientific evaluation framework, experimental hypotheses, and structured templates for future pipeline iterations.

---

## 1. Experiment Methodology

All visual, acoustic, and narrative improvements follow an empirical iteration loop:
1. **Hypothesis Formulation**: What parameter change is expected to yield what measurable improvement?
2. **Controlled Modification**: Change exactly one parameter in `storyboard.json` or model settings.
3. **Deterministic Run**: Execute using a pinned seed and record in `runs.jsonl`.
4. **Multi-Aspect Evaluation**: Assess impact on visual consistency, prompt adherence, audio clarity, and rendering latency.

---

## 2. Planned Experiments Backlog

### EXP-001: Keyframe Visual Consistency Across Steps (FLUX-1 Schnell)
- **Objective**: Determine optimal diffusion inference step count balancing generation speed and fine fabric texture on the grandmother's *Tibeb* embroidery.
- **Hypothesis**: Increasing FLUX-1 Schnell steps from 4 to 8 will improve textile weave sharpness by >20% without exceeding Cloudflare API timeouts.
- **Baseline**: 4 steps, seed 42002.
- **Test Condition**: 8 steps, seed 42002.
- **Status**: Queued for live API evaluation.

### EXP-002: Wan 2.2 TI2V Motion Stability vs Prompt Weighting
- **Objective**: Prevent morphological distortion of grandmother's hands during coffee bean manipulation (shots 03 and 04).
- **Hypothesis**: Decreasing motion bucket intensity and restricting prompt to camera movement will reduce anatomical warping during video diffusion.
- **Status**: Queued for Kaggle GPU execution.

### EXP-003: Sidechain Compression Ducking Ratios for Amharic Narration
- **Objective**: Ensure absolute speech intelligibility across diverse playback hardware (phone speakers vs headphones).
- **Hypothesis**: A sidechain compression ratio of 4:1 with 300ms release avoids audible "pumping" artifacts while maintaining -14 dB background attenuation during Amharic vocal delivery.
- **Status**: Implemented in FFmpeg utility, queued for critical listening evaluation.

---

## 3. Experiment Execution Template

```markdown
### Experiment ID: EXP-XXX
- **Date**: YYYY-MM-DD
- **Target Stage**: [keyframes | shots | narration | music | assembly]
- **Hypothesis**: 
- **Baseline Configuration**:
  - Model:
  - Parameters:
  - Seed:
- **Test Configuration**:
  - Parameters Changed:
- **Measurements**:
  - Generation Duration (sec):
  - Cost / API Units:
  - Visual/Acoustic Observations:
- **Outcome**: [ACCEPTED | REJECTED | INCONCLUSIVE]
- **Artifacts**: Path to outputs
```

