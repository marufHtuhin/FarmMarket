"""Fruit ripeness + disease classification from photos, and grade-based pricing.

Approach: hand-crafted colour/texture features + scikit-learn RandomForest. It is a
transparent, CPU-only BASELINE that trains in minutes. A fine-tuned CNN on PlantVillage
and local field photos should beat it; the `predict` interface is model-agnostic.

Safety rules baked in:
  * No trained model on disk -> ModelNotAvailableError (HTTP 503). Never fake a result.
  * Low confidence or crop mismatch -> grade "REVIEW", no automated price.
  * Images are never stored; only a SHA-256 and the outcome are kept by the API layer.
"""
from __future__ import annotations
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
from PIL import Image, UnidentifiedImageError
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

from ..config import model_dir
from . import torch_vision
from .datasources.plantvillage import crop_of_label, is_healthy_label

FEATURE_VERSION = 1
IMG_SIZE = 96
MAX_IMAGE_BYTES = 5 * 1024 * 1024
RIPENESS_CLASSES = ("unripe", "ripe", "overripe")
MIN_CONFIDENCE = 0.60

# Illustrative grade->price multipliers. Replace with agronomic/market-calibrated values.
GRADE_TABLE = {
    "A": {"multiplier": 1.00, "meaning": "ripe, no disease detected"},
    "B": {"multiplier": 0.85, "meaning": "unripe (needs time) or slightly past peak, no disease detected"},
    "C": {"multiplier": 0.50, "meaning": "overripe or disease detected: sell quickly / processing"},
}


class ModelNotAvailableError(RuntimeError):
    pass


class BadImageError(ValueError):
    pass


def load_image(data: bytes) -> Image.Image:
    if len(data) > MAX_IMAGE_BYTES:
        raise BadImageError("Image too large (max 5 MB)")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
        raise BadImageError("File is not a readable image") from e
    return img.convert("RGB")


def extract_features(img: Image.Image) -> np.ndarray:
    rgb = img.convert("RGB").resize((IMG_SIZE, IMG_SIZE))
    a = np.asarray(rgb, dtype=np.float32) / 255.0
    hsv = np.asarray(rgb.convert("HSV"), dtype=np.float32) / 255.0
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    mask = (s > 0.12) & (v > 0.08)          # drop near-gray / near-black background
    if mask.mean() < 0.05:
        mask = np.ones_like(mask, dtype=bool)
    w = mask.astype(np.float32)
    feats: list[float] = []
    feats += list(np.histogram(h[mask], bins=18, range=(0, 1))[0] / mask.sum())
    feats += list(np.histogram(s[mask], bins=6, range=(0, 1))[0] / mask.sum())
    feats += list(np.histogram(v[mask], bins=6, range=(0, 1))[0] / mask.sum())
    for ch in (a[..., 0], a[..., 1], a[..., 2], s, v):
        feats += [float(ch[mask].mean()), float(ch[mask].std())]
    hd = h * 360
    feats += [float(((hd >= 70) & (hd <= 170) & mask).sum() / mask.sum()),          # green
              float((((hd <= 20) | (hd >= 340)) & (s > 0.35) & mask).sum() / mask.sum()),  # red
              float(((hd > 20) & (hd < 70) & mask).sum() / mask.sum()),             # yellow/orange
              float(((v < 0.35) & (s > 0.2) & mask).sum() / mask.sum())]            # dark/brown lesions
    gray = a.mean(axis=2)
    gx, gy = np.abs(np.diff(gray, axis=1))[:-1, :], np.abs(np.diff(gray, axis=0))[:, :-1]
    g = gx + gy
    lap = np.abs(gray[1:-1, 1:-1] * 4 - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:])
    feats += [float(g.mean()), float(g.std()), float((g > 0.15).mean()), float(lap.var()), float(w.mean())]
    return np.asarray(feats, dtype=np.float32)


@dataclass
class TrainReport:
    task: str
    n_train: int
    n_test: int
    accuracy: float
    macro_f1: float
    classes: list[str]
    confusion: list[list[int]]


def train_classifier(samples: list[tuple[Path | bytes, str]], task: str, out_dir: Path | None = None,
                     dataset_note: str = "", seed: int = 0) -> TrainReport:
    """samples: [(image path or bytes, label)]. Holds out 20% (stratified when possible)."""
    X, y = [], []
    for item, label in samples:
        try:
            img = load_image(item if isinstance(item, bytes) else Path(item).read_bytes())
        except BadImageError:
            continue
        X.append(extract_features(img))
        y.append(label)
    if len(set(y)) < 2:
        raise ValueError("Need at least two classes with readable images")
    X, y = np.stack(X), np.array(y)
    counts = {c: int((y == c).sum()) for c in set(y)}
    strat = y if min(counts.values()) >= 2 else None
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=seed, stratify=strat)
    clf = RandomForestClassifier(n_estimators=300, class_weight="balanced", n_jobs=-1, random_state=seed)
    clf.fit(Xtr, ytr)
    pred = clf.predict(Xte)
    classes = [str(c) for c in clf.classes_]
    report = TrainReport(task, len(ytr), len(yte), round(float(accuracy_score(yte, pred)), 4),
                         round(float(f1_score(yte, pred, average="macro")), 4), classes,
                         confusion_matrix(yte, pred, labels=clf.classes_).tolist())
    out_dir = Path(out_dir or model_dir())
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle = {"model": clf, "classes": classes, "feature_version": FEATURE_VERSION, "task": task,
              "trained_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
              "dataset_note": dataset_note, "metrics": report.__dict__}
    joblib.dump(bundle, out_dir / f"{task}.joblib")
    (out_dir / f"{task}.card.json").write_text(json.dumps(
        {k: v for k, v in bundle.items() if k != "model"}, indent=2))
    return report


_cache: dict[str, dict] = {}


def load_bundle(task: str, directory: Path | None = None) -> dict:
    path = Path(directory or model_dir()) / f"{task}.joblib"
    key = f"{path}:{path.stat().st_mtime_ns}" if path.exists() else str(path)
    if key in _cache:
        return _cache[key]
    if not path.exists():
        raise ModelNotAvailableError(
            f"No trained '{task}' model at {path}. Run scripts/train_vision.py first.")
    # joblib/pickle: only load model files you trained yourself.
    bundle = joblib.load(path)
    if bundle.get("feature_version") != FEATURE_VERSION:
        raise ModelNotAvailableError(f"'{task}' model was built with an incompatible feature version")
    _cache.clear()
    _cache[key] = bundle
    return bundle


def _top(bundle: dict, feats: np.ndarray) -> tuple[str, float, dict[str, float]]:
    proba = bundle["model"].predict_proba(feats.reshape(1, -1))[0]
    i = int(np.argmax(proba))
    return bundle["classes"][i], float(proba[i]), {c: round(float(p), 3) for c, p in zip(bundle["classes"], proba)}


def grade(ripeness: str | None, ripeness_conf: float, disease_label: str | None, disease_conf: float,
          min_conf: float = MIN_CONFIDENCE) -> dict:
    reasons: list[str] = []
    conf = min([c for c in (ripeness_conf if ripeness else None, disease_conf if disease_label else None)
                if c is not None] or [0.0])
    if ripeness is None and disease_label is None:
        return {"grade": "REVIEW", "price_multiplier": None, "confidence": 0.0,
                "needs_manual_review": True, "reasons": ["No model produced a prediction"]}
    if conf < min_conf:
        return {"grade": "REVIEW", "price_multiplier": None, "confidence": round(conf, 3),
                "needs_manual_review": True,
                "reasons": [f"Model confidence {conf:.0%} is below the {min_conf:.0%} threshold; manual check needed"]}
    diseased = disease_label is not None and not is_healthy_label(disease_label)
    if diseased:
        g = "C"; reasons.append(f"Possible disease detected: {disease_label.replace('___', ' - ').replace('_', ' ')}")
    elif ripeness == "overripe":
        g = "C"; reasons.append("Overripe")
    elif ripeness == "unripe":
        g = "B"; reasons.append("Unripe: price reflects time-to-ripen")
    elif ripeness == "ripe":
        g = "A"; reasons.append("Ripe, no disease detected")
    else:
        g = "B"; reasons.append("Healthy; ripeness not assessed")
    return {"grade": g, "price_multiplier": GRADE_TABLE[g]["multiplier"], "confidence": round(conf, 3),
            "needs_manual_review": False, "reasons": reasons}


def assess(image_bytes: bytes, crop: str | None = None, directory: Path | None = None) -> dict:
    """Grade one photo. Per task, the PyTorch model is tried first when a
    checkpoint exists (MODEL_DIR/torch/<task>/best.pt + config.json); the
    scikit-learn baseline is the fallback. Each task picks its backend
    independently. Grading, confidence thresholds, REVIEW handling and price
    logic are identical regardless of backend.

    The result gains "model": {task: "torch-<backbone>" | "sklearn-randomforest"
    | "unavailable"} and "notes": {task: "model_not_trained"} for tasks with
    no model at all. A 503 (ModelNotAvailableError) is raised only when NO
    model exists for EITHER task; a single missing task degrades gracefully.
    """
    img = load_image(image_bytes)
    feats = extract_features(img)
    sha = hashlib.sha256(image_bytes).hexdigest()
    ripeness = disease = None
    r_conf = d_conf = 0.0
    r_probs = d_probs = {}
    versions, missing = [], []
    backends: dict[str, str] = {}
    notes: dict[str, str] = {}
    load_warnings: list[str] = []
    for task in ("ripeness", "disease"):
        label = conf = probs = None
        # Torch path first; a missing/broken torch setup falls through to sklearn.
        try:
            pred = torch_vision.predict_torch(task, image_bytes, directory)
        except torch_vision.TorchNotInstalledError:
            pred = None  # checkpoint exists but torch is not installed: use sklearn
        except Exception as e:  # noqa: BLE001 - a corrupt torch checkpoint must not 500 the API
            pred = None
            load_warnings.append(f"'{task}' torch model failed to load ({type(e).__name__}); "
                                 "fell back to the scikit-learn baseline")
        if pred is not None:
            label, conf, probs = pred["label"], pred["confidence"], pred["per_class"]
            versions.append(f"{task}@{pred['version']}")
            backends[task] = f"torch-{pred['backbone']}"
        else:
            try:
                b = load_bundle(task, directory)
            except ModelNotAvailableError:
                missing.append(task)
                backends[task] = "unavailable"
                notes[task] = "model_not_trained"
                continue
            label, conf, probs = _top(b, feats)
            versions.append(f"{task}@{b['trained_at']}")
            backends[task] = "sklearn-randomforest"
        if task == "ripeness":
            ripeness, r_conf, r_probs = label, conf, probs
        else:
            disease, d_conf, d_probs = label, conf, probs
    if len(missing) == 2:
        raise ModelNotAvailableError("No vision models are trained yet. Run scripts/train_vision.py.")
    result = grade(ripeness, r_conf, disease, d_conf)
    warnings = [f"'{t}' model not available; grade uses the other signal only" for t in missing]
    if crop and disease and crop_of_label(disease) and crop.lower() not in crop_of_label(disease):
        result.update(grade="REVIEW", price_multiplier=None, needs_manual_review=True)
        result["reasons"].append(f"Disease model saw '{crop_of_label(disease)}' but the listing says '{crop}'")
    model_warnings = []
    if "sklearn-randomforest" in backends.values():
        model_warnings.append("Baseline colour/texture model; validate on local field photos before relying on prices.")
    if any(v.startswith("torch-") for v in backends.values()):
        model_warnings.append("PyTorch model; validate on local field photos before relying on prices.")
    result.update(image_sha256=sha, ripeness=ripeness, ripeness_probabilities=r_probs,
                  disease=disease, disease_probabilities=d_probs, model_version=";".join(versions),
                  model=backends, notes=notes,
                  warnings=warnings + load_warnings + model_warnings)
    return result


def suggest_price(reference_price: float, multiplier: float | None) -> float | None:
    return None if multiplier is None else round(reference_price * multiplier, 2)
