# FarmMarket computer vision — PyTorch transfer learning

CPU-only training + evaluation for the two vision tasks behind
`POST /api/v1/vision/assess`: **disease** classification and **ripeness**
classification. The backend prefers a PyTorch checkpoint when one exists and
falls back to the scikit-learn RandomForest baseline otherwise (per task,
independently).

> **No trained model ships with this repo.** The checkpoints below are
> produced by *you*, from *your* labelled photos. Nothing in this package
> downloads a dataset; the PlantVillage steps describe where to get one.

## Install (CPU-only)

```bash
pip install --index-url https://download.pytorch.org/whl/cpu -r backend/requirements-ml.txt
```

Torch is an **optional** dependency: the API runs fine without it
(`GET /api/v1/vision/status` reports `torch_installed: false` and the
scikit-learn baseline serves all predictions).

## 1. Prepare data

### Disease — PlantVillage (disease labels only)

1. Download PlantVillage from Kaggle (`emmarex/plantdisease`, ~2 GB) or the
   PlantVillage project site, and unzip it.
2. The dataset is already in `<root>/<Crop>___<Condition>/*.jpg` folders
   (e.g. `Tomato___Early_blight`, `Tomato___healthy`). Use it as-is — the
   trainer makes a stratified train/val split when no `train/` + `val/`
   subfolders exist.
3. Optionally cap the size: keep only the crops you serve, and at most a few
   hundred images per class for a first run.
4. **Hold out real field photos** from your target region as a test set.
   PlantVillage images are lab-background shots; accuracy on them overstates
   accuracy on farm photos.

### Ripeness — your own labelled photos

PlantVillage has **no ripeness labels**. Collect and label your own photos
into exactly these folders (the trainer rejects anything else):

```
data/ripeness/
  train/
    unripe/  partially_ripe/  ripe/  overripe/
  val/
    unripe/  partially_ripe/  ripe/  overripe/
```

…or the flat equivalent `data/ripeness/<class>/*.jpg` (the trainer splits it
80/20, stratified, seeded). Aim for ≥100 photos per class, mixed lighting
and backgrounds. Note the backend grades `partially_ripe` as B (same as
`unripe` — "needs time").

## 2. Train

From the repo root:

```bash
# Disease (PlantVillage layout)
python -m ai_services.computer_vision.train \
  --data data/plantvillage --task disease --backbone resnet18 \
  --epochs 10 --batch-size 32 --lr 1e-3 \
  --out backend/models/torch/disease

# Ripeness (your labelled photos)
python -m ai_services.computer_vision.train \
  --data data/ripeness --task ripeness --backbone resnet18 \
  --epochs 10 --out backend/models/torch/ripeness
```

Options: `--backbone mobilenet_v3_small` (smaller, faster on weak hardware),
`--no-pretrained` (random init — offline use / smoke tests), `--val-split`
(flat trees only), `--seed`, `--num-workers`, `--patience` (early stopping,
default 3 epochs without val improvement).

Each run writes into `--out`:

| file | contents |
| --- | --- |
| `best.pt` | best checkpoint by val accuracy: `{state_dict, backbone, classes, task, config}` |
| `last.pt` | checkpoint from the final epoch |
| `config.json` | task, backbone, classes, hyper-parameters, `trained_at`, `best_val_acc` |
| `history.json` | per-epoch `train_loss` / `train_acc` / `val_loss` / `val_acc` |

**Where checkpoints go (what the API looks for):**
`$MODEL_DIR/torch/<task>/best.pt` + `config.json`
(default `$MODEL_DIR` is `backend/models/`). Both files must be present;
the API ignores a lone `best.pt` without its `config.json`.

Training is CPU-only and single-process. Expect roughly 1–3 minutes per
epoch for a few thousand 224×224 images on a modern laptop CPU; start with
`--epochs 3` to sanity-check the pipeline before a full run.

## 3. Evaluate

```bash
python -m ai_services.computer_vision.evaluate \
  --checkpoint backend/models/torch/disease/best.pt \
  --data data/plantvillage --split val --out eval_disease.json
```

Prints a per-class precision/recall/F1 table + confusion matrix, and writes
the same as JSON. Accuracy is always reported together with the number of
evaluated images and the class list — a bare accuracy number on a small or
skewed set misleads. Evaluate on held-out **field** photos, not only on the
PlantVillage val split, before trusting a grade or a price.

## 4. Serve

Restart (or just call) the API — the backend discovers checkpoints on first
use and caches them:

```bash
curl localhost:8000/api/v1/vision/status
# {"torch_installed": true,
#  "torch_models": {"ripeness": "resnet18@2026-11-15T...", "disease": null},
#  "sklearn_models": {...}, "grade_table": {...}, "min_confidence": 0.6}
```

`POST /api/v1/vision/assess` then reports, per task, which backend answered
in its `model` field: `"torch-resnet18"`, `"sklearn-randomforest"`, or
`"unavailable"` (with a `model_not_trained` note). Grading, confidence
thresholds and price logic are identical regardless of backend.

## Smoke test (no real data)

```bash
python - <<'EOF'
# Tiny synthetic 2-class tree, just to exercise the plumbing.
from pathlib import Path
import numpy as np
from PIL import Image
rng = np.random.default_rng(0)
for split, n in (("train", 8), ("val", 4)):
    for cls, col in (("class_a", (200, 40, 35)), ("class_b", (70, 150, 60))):
        d = Path("data/smoke") / split / cls
        d.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            Image.fromarray(np.full((64, 64, 3), col, dtype="uint8")).save(d / f"{i}.jpg")
EOF
python -m ai_services.computer_vision.train --data data/smoke --task disease \
  --epochs 1 --no-pretrained --out /tmp/smoke_torch
python -m ai_services.computer_vision.evaluate \
  --checkpoint /tmp/smoke_torch/best.pt --data data/smoke --split val
rm -rf data/smoke /tmp/smoke_torch   # delete the smoke artefacts afterwards
```

Metrics from such a run are **meaningless as accuracy** — they only prove
the pipeline runs end to end.
