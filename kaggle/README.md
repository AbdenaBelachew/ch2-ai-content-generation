# Kaggle GPU Execution Guide: Wan 2.2 TI2V-5B & ACE-Step 1.5

This directory contains standalone execution scripts, batch manifests, and Jupyter notebooks for running GPU workloads on Kaggle's free GPU tier (T4x2 or P100) or Google Cloud Vertex AI / RunPod.

---

## 1. Workload Architecture

| Workload | Model | Hardware | Notebook / Script | Output |
| :--- | :--- | :--- | :--- | :--- |
| **Moving Shots** | Wan 2.2 TI2V-5B | Kaggle GPU (T4 x 2 or P100 16GB) | `kaggle/wan2_ti2v_notebook.ipynb` | `outputs/shots/{shot_id}.mp4` |
| **Soundtrack** | ACE-Step 1.5 | Kaggle GPU (T4 16GB) | `kaggle/ace_step_music_notebook.ipynb` | `outputs/music/soundtrack.wav` |

---

## 2. Interactive Notebook Execution on Kaggle (Turnkey)

### A. Video Generation (Wan 2.2 TI2V-5B)
1. **Prepare Batch**: Run `python -m pipeline.cli shots` locally. This ensures all keyframes in `outputs/keyframes/` and `kaggle/wan_batch.json` are generated.
2. **Upload Notebook**: On [Kaggle](https://www.kaggle.com/code), click **New Notebook** $\to$ **File** $\to$ **Import Notebook** $\to$ upload `kaggle/wan2_ti2v_notebook.ipynb`.
3. **Attach Dataset**: Upload `outputs/keyframes/` and `kaggle/wan_batch.json` as a Kaggle dataset named `heritage-short-inputs` and attach it to the notebook.
4. **Set Accelerator**: In the right sidebar under **Notebook options**, select **GPU T4 x 2** (or **P100**).
5. **Run All**: Click **Run All**. The notebook renders each 7.5s video clip and packages them into `/kaggle/working/outputs_shots.zip`.
6. **Import to Pipeline**: Download `outputs_shots.zip` and extract its contents into your local workspace at `outputs/shots/`.

### B. Music Generation (ACE-Step 1.5)
1. **Prepare Batch**: Run `python -m pipeline.cli music` locally to generate `kaggle/acestep_batch.json`.
2. **Upload Notebook**: Import `kaggle/ace_step_music_notebook.ipynb` to Kaggle.
3. **Run All**: The notebook generates the 78s traditional Ethiopian acoustic soundtrack (*Masenqo*, *Washint*, *Krar*, *Kebero* at 68 BPM) and saves it to `/kaggle/working/outputs/music/soundtrack.wav`.
4. **Import to Pipeline**: Download `soundtrack.wav` into your local workspace at `outputs/music/soundtrack.wav`.

---

## 3. Automated CLI Execution via Kaggle API

If you have Kaggle API credentials configured in `.env` (`KAGGLE_USERNAME` and `KAGGLE_KEY`):

```bash
# Push and execute video generation kernel
kaggle kernels push -p kaggle/

# Check status
kaggle kernels status <username>/wan-2-2-ti2v-heritage-short

# Download outputs directly into pipeline directory
kaggle kernels output <username>/wan-2-2-ti2v-heritage-short -p outputs/shots/
```

---

## 4. Pipeline Integration & Caching

Once output files are placed into `outputs/shots/` and `outputs/music/`:
```bash
python -m pipeline.cli status
python -m pipeline.cli assemble
```
The content-addressed caching engine automatically verifies file hashes and proceeds to assemble the final 9:16 and 16:9 master MP4 films.
