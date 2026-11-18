"""ImageFolder loaders for the FarmMarket vision tasks.

Supported layouts (class names come from folder names):

  Disease (PlantVillage-style):
      data/train/Tomato___Early_blight/*.jpg
      data/val/Tomato___healthy/*.jpg
      ... or a flat tree data/<disease_class>/*.jpg (train.py splits it)

  Ripeness (your own labelled photos -- PlantVillage has disease labels only):
      data/ripeness/train/<unripe|partially_ripe|ripe|overripe>/*.jpg
      data/ripeness/val/<...>/*.jpg
      ... or flat: data/ripeness/<class>/*.jpg (train.py splits it)

Both layouts are accepted: if train/ + val/ subfolders exist they are used
directly; otherwise a stratified, seeded split of the flat tree is made.

Train transforms: RandomResizedCrop(224), RandomHorizontalFlip, ColorJitter,
ImageNet normalisation. Val transforms: Resize(256) + CenterCrop(224) +
normalisation. The backend inference service (app/services/torch_vision.py)
replicates the VAL transforms exactly -- keep them in sync.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset, Subset, WeightedRandomSampler
from torchvision import datasets, transforms

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
RIPENESS_CLASSES = ("unripe", "partially_ripe", "ripe", "overripe")
TASKS = ("disease", "ripeness")


class DatasetLayoutError(ValueError):
    """Raised when a dataset folder does not match the expected layout."""


def train_transforms() -> transforms.Compose:
    return transforms.Compose([
        transforms.RandomResizedCrop(IMAGE_SIZE),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])


def val_transforms() -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(IMAGE_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])


def _class_dirs(split_dir: Path) -> list[Path]:
    return sorted(p for p in split_dir.iterdir() if p.is_dir())


def _count_images(split_dir: Path) -> dict[str, int]:
    counts = {}
    for cls_dir in _class_dirs(split_dir):
        n = sum(1 for f in cls_dir.rglob("*") if f.is_file() and f.suffix.lower() in IMG_EXT)
        if n:
            counts[cls_dir.name] = n
    return counts


def _check_ripeness_classes(classes: list[str]) -> None:
    unknown = sorted(set(classes) - set(RIPENESS_CLASSES))
    if unknown:
        raise DatasetLayoutError(
            f"Ripeness folders must be named {RIPENESS_CLASSES}; found extra: {unknown}")


def validate_layout(root: str | Path, task: str) -> dict[str, dict[str, int]]:
    """Validate a dataset tree; returns {split: {class: n_images}}.

    Accepts either split folders (train/ + val/) or a flat class tree.
    Raises DatasetLayoutError with a clear message on any problem.
    """
    if task not in TASKS:
        raise DatasetLayoutError(f"Unknown task {task!r}; choose from {TASKS}")
    root = Path(root)
    if not root.is_dir():
        raise DatasetLayoutError(f"Dataset folder not found: {root}")
    train_dir, val_dir = root / "train", root / "val"
    if train_dir.is_dir() or val_dir.is_dir():
        if not train_dir.is_dir():
            raise DatasetLayoutError(f"Found {val_dir} but no {train_dir}; "
                                     "provide both train/ and val/ splits, or a flat class tree.")
        if not val_dir.is_dir():
            raise DatasetLayoutError(f"Found {train_dir} but no {val_dir}; "
                                     "provide both train/ and val/ splits, or a flat class tree.")
        layout = {"train": _count_images(train_dir), "val": _count_images(val_dir)}
    else:
        layout = {"all": _count_images(root)}
    for split, counts in layout.items():
        if not counts:
            raise DatasetLayoutError(
                f"No image folders with {sorted(IMG_EXT)} files under {root / split if split != 'all' else root}. "
                f"Expected <root>/{split}/<class>/*.jpg (or a flat <root>/<class>/*.jpg tree).")
        if len(counts) < 2:
            raise DatasetLayoutError(
                f"Split {split!r} has only {len(counts)} class folder(s) ({sorted(counts)}); "
                "need at least 2 classes to train a classifier.")
    if task == "ripeness":
        _check_ripeness_classes([c for counts in layout.values() for c in counts])
    if "train" in layout and "val" in layout:
        missing = sorted(set(layout["train"]) - set(layout["val"]))
        if missing:
            raise DatasetLayoutError(f"Classes {missing} appear in train/ but not in val/; "
                                     "every class needs validation images.")
    return layout


def _stratified_split(dataset: Dataset, val_fraction: float, seed: int
                      ) -> tuple[Subset, Subset]:
    """Stratified train/val split of an ImageFolder-style dataset."""
    targets = list(dataset.targets)  # type: ignore[attr-defined]
    by_class: dict[int, list[int]] = {}
    for i, t in enumerate(targets):
        by_class.setdefault(t, []).append(i)
    gen = torch.Generator().manual_seed(seed)
    train_idx, val_idx = [], []
    for indices in by_class.values():
        perm = torch.randperm(len(indices), generator=gen).tolist()
        n_val = max(1, round(len(indices) * val_fraction)) if len(indices) > 1 else 0
        val_idx += [indices[j] for j in perm[:n_val]]
        train_idx += [indices[j] for j in perm[n_val:]]
    if not val_idx:
        raise DatasetLayoutError("Cannot make a validation split: every class has a single image.")
    return Subset(dataset, train_idx), Subset(dataset, val_idx)


def _balanced_sampler(dataset: Dataset) -> WeightedRandomSampler:
    """WeightedRandomSampler so minority classes are oversampled in training."""
    targets = list(dataset.targets) if hasattr(dataset, "targets") else [  # type: ignore[attr-defined]
        dataset.dataset.targets[i] for i in dataset.indices]  # type: ignore[attr-defined]
    counts = Counter(targets)
    class_weight = {c: 1.0 / n for c, n in counts.items()}
    weights = [class_weight[t] for t in targets]
    return WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)


@dataclass
class Loaders:
    train: DataLoader
    val: DataLoader
    classes: list[str]
    n_train: int
    n_val: int
    layout: dict[str, dict[str, int]]


def build_loaders(root: str | Path, task: str, batch_size: int = 32,
                  val_split: float = 0.2, seed: int = 0,
                  num_workers: int = 0) -> Loaders:
    """Train + val loaders for `task`, with class balancing on the train loader.

    Uses train/val subfolders when present, otherwise makes a stratified
    seeded split of the flat class tree.
    """
    root = Path(root)
    layout = validate_layout(root, task)
    if "train" in layout:
        train_ds = datasets.ImageFolder(root / "train", transform=train_transforms())
        val_ds = datasets.ImageFolder(root / "val", transform=val_transforms())
        classes = train_ds.classes
        if val_ds.classes != classes:
            raise DatasetLayoutError("train/ and val/ class folders differ: "
                                     f"{classes} vs {val_ds.classes}")
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False,
                                  sampler=_balanced_sampler(train_ds), num_workers=num_workers)
        val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    else:
        full = datasets.ImageFolder(root, transform=train_transforms())
        classes = full.classes
        train_ds, val_ds = _stratified_split(full, val_split, seed)
        # Val subset must use val transforms: wrap it in a second ImageFolder.
        val_full = datasets.ImageFolder(root, transform=val_transforms())
        val_ds = Subset(val_full, val_ds.indices)  # type: ignore[attr-defined]
        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False,
                                  sampler=_balanced_sampler(train_ds), num_workers=num_workers)
        val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    return Loaders(train_loader, val_loader, classes, len(train_loader.dataset),
                   len(val_loader.dataset), layout)


def build_eval_loader(root: str | Path, split: str = "val", batch_size: int = 32,
                      num_workers: int = 0) -> tuple[DataLoader, list[str]]:
    """Loader for evaluating a checkpoint on one split (default: val).

    Uses <root>/<split>/ when it exists, else the flat <root>/<class>/ tree.
    """
    root = Path(root)
    split_dir = root / split
    if split_dir.is_dir():
        ds = datasets.ImageFolder(split_dir, transform=val_transforms())
    elif root.is_dir() and _count_images(root):
        ds = datasets.ImageFolder(root, transform=val_transforms())
    else:
        raise DatasetLayoutError(f"No {split!r} split (and no flat class tree) under {root}")
    if len(ds.classes) < 2:
        raise DatasetLayoutError(f"Evaluation set under {split_dir or root} has "
                                 f"fewer than 2 classes ({ds.classes})")
    return DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=num_workers), ds.classes
