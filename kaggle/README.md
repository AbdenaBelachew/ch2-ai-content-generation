# Kaggle GPU Execution Guide: Wan 2.2 TI2V-5B & ACE-Step 1.5

This directory contains standalone execution scripts and batch configurations for running heavy GPU workloads on Kaggle's free GPU tier (T4x2 or P100) or Google Cloud Vertex / RunPod.

---

## 1. Workload Architecture

| Workload | Model | Hardware Recommended | Input | Output |
| :--- | :--- | :--- | :--- | :--- |
| **Moving Shots** | Wan 2.2 TI2V-5B | Kaggle GPU (T4 x 2 or P100 16GB) | `kaggle/wan_batch.json` + Keyframe PNGs | `outputs/shots/{shot_id}.mp4` |
| **Soundtrack** | ACE-Step 1.5 | Kaggle GPU (T4 16GB) | `kaggle/acestep_batch.json` | `outputs/music/soundtrack.wav` |

---

## 2. Automated Execution via Kaggle API

If you have Kaggle API credentials configured in `.env` (`KAGGLE_USERNAME` and `KAGGLE_KEY`):

1. **Verify Connection**:
   ```bash
   python -m pipeline.cli status
   ```

2. **Push and Execute Video Generation**:
   ```bash
   # Generates kaggle/wan_batch.json
   python -m pipeline.cli shots
   ```

3. **Retrieve Output Files**:
   Once execution completes on Kaggle:
   ```bash
   kaggle kernels output <username>/wan-2-2-ti2v-heritage-short -p outputs/shots/
   ```

---

## 3. Manual Fallback Workflow (No API Setup Required)

If automated API execution is not configured, follow this step-by-step manual workflow on kaggle.com:

### Phase A: Video Generation (Wan 2.2 TI2V-5B)
1. **Prepare Inputs**:
   - Run `python -m pipeline.cli keyframes` to ensure all keyframes exist in `outputs/keyframes/`.
   - Run `python -m pipeline.cli shots` to produce `kaggle/wan_batch.json`.
2. **Create Kaggle Dataset**:
   - On [Kaggle](https://www.kaggle.com/datasets), click **New Dataset**.
   - Upload the `outputs/keyframes/` folder and `kaggle/wan_batch.json`.
   - Name the dataset `heritage-short-inputs`.
3. **Launch Notebook**:
   - On Kaggle, click **New Notebook**.
   - Under **Notebook Options** (right sidebar):
     - **Accelerator**: GPU T4 x 2 or P100.
     - **Internet**: ON.
   - Attach your dataset `heritage-short-inputs`.
   - Copy and paste the code from [wan2_ti2v_runner.py](file:///d:/tenx/challenges/ch2-ai-content-generation/kaggle/wan2_ti2v_runner.py) into the notebook cells.
   - Click **Run All**.
4. **Download Video Clips**:
   - Download the generated `.mp4` video files from `/kaggle/working/outputs/`.
   - Place them directly into your local workspace at:
     ```
     outputs/shots/shot_01.mp4
     outputs/shots/shot_02.mp4
     ...
     outputs/shots/shot_10.mp4
     ```

### Phase B: Music Generation (ACE-Step 1.5)
1. **Prepare Music Payload**:
   - Run `python -m pipeline.cli music` to produce `kaggle/acestep_batch.json`.
2. **Launch Kaggle Notebook**:
   - Open a Kaggle GPU notebook with Internet ON.
   - Copy and paste code from [ace_step_runner.py](file:///d:/tenx/challenges/ch2-ai-content-generation/kaggle/ace_step_runner.py).
   - Click **Run All**.
3. **Download Soundtrack**:
   - Download `soundtrack.wav`.
   - Place it into your local workspace at:
     ```
     outputs/music/soundtrack.wav
     ```

---

## 4. Local Assembly Verification

Once the output files are placed in `outputs/shots/` and `outputs/music/`, run:
```bash
python -m pipeline.cli status
python -m pipeline.cli assemble
```
The caching system will detect the files, verify their presence and hashes, and assemble the final 9:16 and 16:9 MP4 films.

