# Kaggle GPU runs: Wan 2.2 TI2V-5B (video) and ACE-Step 1.5 (music)

| File | Purpose |
| :--- | :--- |
| `wan2_ti2v_runner.py` | Real Wan 2.2 TI2V-5B image-to-video logic (single source of truth) |
| `ace_step_runner.py` | Real ACE-Step 1.5 text-to-music logic |
| `wan2_ti2v_notebook.ipynb` | Thin notebook: install, GPU check, smoke test on one shot, full batch |
| `ace_step_music_notebook.ipynb` | Thin notebook: install ACE-Step, generate, package |
| `bundle.py` | `pack` builds the upload bundle; `unpack` validates and imports results |

> **Status: written from the official docs, not yet executed on a Kaggle GPU.** The first real run is
> the verification. The runners never write placeholders: if a model fails to load or a file comes out
> tiny, they raise. Treat any "success" as real only after `bundle.py unpack` accepts the files.

## 1. Prepare inputs (on your PC)

```bash
python -m pipeline.cli keyframes      # keyframes must exist
make kaggle-pack                      # or: python kaggle/bundle.py pack
```

This creates `outputs/kaggle_bundle/` (`wan_batch.json`, `acestep_batch.json`, `keyframes/`, both runners)
and a `.zip`.

## 2. Kaggle setup (once)

1. Sign in at kaggle.com and **verify your phone number** (required for GPU and Internet access).
2. **Datasets, New Dataset**: upload the *contents* of `outputs/kaggle_bundle/` and name it `heritage-short-inputs`.
3. **Code, New Notebook, File, Import Notebook**: import a notebook from this folder.
4. In the notebook sidebar: **Add Input** and attach `heritage-short-inputs`. Set **Accelerator** to GPU (T4 x2 or P100) and **Internet** to On (weights download from Hugging Face).

## 3. Video (Wan 2.2 TI2V-5B)

1. Run cells 1 to 5. Cell 4 generates **only `shot_01`**, so you can check quality, time and memory first.
2. If you hit CUDA out-of-memory, lower `MAX_AREA` or `MAX_FRAMES` in cell 4 (`MAX_FRAMES` must be 4k+1, e.g. 81).
3. Run cell 6 (all shots), then cell 7. Download `/kaggle/working/outputs_shots.zip` from the **Output** tab.

Notes: the model's native clip is 24 fps. Defaults give 121 frames (about 5 s) at about 480x832 area. Planned shots are 7.5 s, so assembly holds the last frame to fill the slot. It never time-stretches. Raise `MAX_FRAMES` if your GPU allows.

## 4. Music (ACE-Step 1.5)

Import the second notebook, attach the same dataset, run all cells, and download `soundtrack_bundle.zip`.
If the install cell fails, the ACE-Step docs describe a `uv sync` route; see https://github.com/ACE-Step/ACE-Step-1.5.
On out-of-memory set `THINKING = False`.

## 5. Import results (on your PC)

```bash
python kaggle/bundle.py unpack outputs_shots.zip soundtrack_bundle.zip
python -m pipeline.cli status
python -m pipeline.cli assemble
```

`unpack` rejects placeholder or truncated files, copies good ones into `outputs/shots/` and
`outputs/music/`, updates the cache, and appends `runs.jsonl` records using only the timings Kaggle
measured (`gpu_minutes` is the generation time; model load time is excluded).

## If something fails

- **`WanImageToVideoPipeline` rejects the checkpoint:** the TI2V-5B model card documents text-to-video only. Copy the full error into `FAILURES.md`; the image-conditioned path is the unverified part.
- **ACE-Step signature errors:** `ace_step_runner.py` only passes keyword arguments the installed version accepts and prints those it skipped. Compare with `docs/en/INFERENCE.md` in the ACE-Step repo.
- **Automated `kaggle kernels push`:** not verified (the API smoke test returned HTTP 404). The manual notebook route above is the supported path.
