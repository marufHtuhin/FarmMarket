"""Dataset indexers for image training.

PlantVillage layout: <root>/<Crop>___<Condition>/*.jpg  (e.g. Tomato___Early_blight).
PlantVillage has NO ripeness labels. Ripeness needs its own folder tree:
<root>/<unripe|ripe|overripe>/*.jpg (collect locally or use another open dataset).
"""
from __future__ import annotations
from pathlib import Path
import random

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def index_folder_dataset(root: str | Path, max_per_class: int | None = None,
                         seed: int = 0) -> list[tuple[Path, str]]:
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset folder not found: {root}")
    rng = random.Random(seed)
    samples: list[tuple[Path, str]] = []
    for cls_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        files = sorted(f for f in cls_dir.rglob("*") if f.suffix.lower() in IMG_EXT)
        rng.shuffle(files)
        if max_per_class:
            files = files[:max_per_class]
        samples += [(f, cls_dir.name) for f in files]
    if not samples:
        raise ValueError(f"No images found under {root}")
    return samples


def is_healthy_label(label: str) -> bool:
    return label.lower().endswith("healthy")


def crop_of_label(label: str) -> str:
    return label.split("___")[0].replace("_", " ").lower() if "___" in label else ""
