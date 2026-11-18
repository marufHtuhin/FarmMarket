"""PyTorch inference wrapper for the vision API (optional dependency).

Reads checkpoints produced by ai_services/computer_vision/train.py from
MODEL_DIR/torch/<task>/best.pt + config.json. Torch is imported LAZILY inside
functions, so this module -- and the whole API -- imports and runs fine when
torch is not installed:

  * no checkpoint on disk            -> load_torch_model / predict_torch return None
  * checkpoint present, torch absent -> load_torch_model returns None,
                                        predict_torch raises TorchNotInstalledError
  * torch present                    -> normal inference

Preprocessing mirrors the VAL transforms in
ai_services.computer_vision.dataset.val_transforms exactly (Resize(256) +
CenterCrop(224) + ImageNet normalisation), implemented with PIL + torch only
so the backend does not depend on the training package or on torchvision
transforms at inference time. The architecture (resnet18 / mobilenet_v3_small)
is rebuilt here from torchvision to load the state dict; keep the head
replacement in sync with ai_services.computer_vision.model.build_model.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

from PIL import Image

from ..config import model_dir

IMAGE_SIZE = 224
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)
TASKS = ("ripeness", "disease")


class TorchNotInstalledError(RuntimeError):
    """A torch checkpoint exists but torch/torchvision is not installed."""


def torch_available() -> bool:
    """True when torch AND torchvision can be imported (no import performed).

    Defensive: a half-installed torch (find_spec raising) counts as unavailable.
    """
    try:
        return (importlib.util.find_spec("torch") is not None
                and importlib.util.find_spec("torchvision") is not None)
    except (ImportError, ValueError, OSError):
        return False


def _checkpoint_paths(task: str, directory: Path | None = None) -> tuple[Path, Path]:
    base = Path(directory or model_dir()) / "torch" / task
    return base / "best.pt", base / "config.json"


def torch_model_version(task: str, directory: Path | None = None) -> str | None:
    """Version string for a usable torch checkpoint, without importing torch.

    Returns e.g. "resnet18@2026-11-15T12:00:00Z", or None when no usable
    checkpoint exists (best.pt AND config.json must both be present).
    """
    ckpt, cfg_path = _checkpoint_paths(task, directory)
    if not ckpt.exists() or not cfg_path.exists():
        return None
    try:
        cfg = json.loads(cfg_path.read_text())
    except (OSError, ValueError):
        return None
    return f"{cfg.get('backbone', 'torch')}@{cfg.get('trained_at', 'unknown')}"


def _build_model(backbone: str, num_classes: int):
    """Rebuild the inference architecture (weights=None; state dict loaded by caller)."""
    import torch  # noqa: F401  (kept local: torch is optional)
    from torch import nn
    from torchvision import models
    if backbone == "resnet18":
        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    elif backbone == "mobilenet_v3_small":
        model = models.mobilenet_v3_small(weights=None)
        last = model.classifier[-1]
        model.classifier[-1] = nn.Linear(last.in_features, num_classes)
    else:
        raise ValueError(f"Unsupported backbone in checkpoint: {backbone!r}")
    model.eval()
    return model


_cache: dict[str, dict] = {}


def clear_cache() -> None:
    """Drop cached torch models (tests; also lets a retrained checkpoint reload)."""
    _cache.clear()


def load_torch_model(task: str, directory: Path | None = None) -> dict | None:
    """Load (cached) a torch checkpoint, or None when unavailable.

    Never raises for a missing model or a missing torch install; a corrupt
    checkpoint raises, and callers that fall back (vision.assess) handle it.
    """
    ckpt, cfg_path = _checkpoint_paths(task, directory)
    if not ckpt.exists() or not cfg_path.exists():
        return None
    if not torch_available():
        return None
    key = f"{ckpt}:{ckpt.stat().st_mtime_ns}"
    if key in _cache:
        return _cache[key]
    import torch
    cfg = json.loads(cfg_path.read_text())
    payload = torch.load(ckpt, map_location="cpu", weights_only=True)
    for field in ("state_dict", "backbone", "classes"):
        if field not in payload:
            raise ValueError(f"Checkpoint {ckpt} is missing {field!r}")
    model = _build_model(payload["backbone"], len(payload["classes"]))
    model.load_state_dict(payload["state_dict"])
    bundle = {"model": model, "classes": list(payload["classes"]),
              "backbone": payload["backbone"], "task": task,
              "config": cfg, "version": cfg.get("trained_at", "unknown")}
    _cache.clear()
    _cache[key] = bundle
    return bundle


def _preprocess(image_bytes: bytes):
    """Val-transform preprocessing (PIL + torch), mirroring dataset.val_transforms."""
    import torch
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception as e:  # noqa: BLE001 - any unreadable image is a plain error
        raise ValueError("File is not a readable image") from e
    img = img.convert("RGB")
    # torchvision Resize(256): shorter edge -> 256, other edge scaled (floor).
    w, h = img.size
    if w < h:
        img = img.resize((256, int(256 * h / w)), Image.BILINEAR)
    else:
        img = img.resize((int(256 * w / h), 256), Image.BILINEAR)
    # torchvision CenterCrop(224).
    w, h = img.size
    left, top = (w - IMAGE_SIZE) // 2, (h - IMAGE_SIZE) // 2
    img = img.crop((left, top, left + IMAGE_SIZE, top + IMAGE_SIZE))
    import numpy as np
    arr = np.asarray(img, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(arr).permute(2, 0, 1)  # HWC -> CHW, like ToTensor
    mean = torch.tensor(_IMAGENET_MEAN).view(3, 1, 1)
    std = torch.tensor(_IMAGENET_STD).view(3, 1, 1)
    return (tensor - mean) / std


def predict_torch(task: str, image_bytes: bytes, directory: Path | None = None) -> dict | None:
    """Run the torch model for `task`, or None when no checkpoint exists.

    Raises TorchNotInstalledError when a checkpoint exists but torch is not
    installed. Returns {"label", "confidence", "per_class", "backbone", "version"}.
    """
    ckpt, cfg_path = _checkpoint_paths(task, directory)
    if not ckpt.exists() or not cfg_path.exists():
        return None
    if not torch_available():
        raise TorchNotInstalledError(
            f"A torch '{task}' checkpoint exists at {ckpt} but torch/torchvision "
            "is not installed. Install backend/requirements-ml.txt (CPU wheels) "
            "or remove the checkpoint to use the scikit-learn baseline.")
    import torch
    bundle = load_torch_model(task, directory)
    if bundle is None:  # pragma: no cover - guarded above, kept for safety
        return None
    tensor = _preprocess(image_bytes)
    with torch.no_grad():
        probs = torch.softmax(bundle["model"](tensor.unsqueeze(0)), dim=1)[0]
    i = int(torch.argmax(probs))
    classes = bundle["classes"]
    return {"label": classes[i], "confidence": float(probs[i]),
            "per_class": {c: round(float(p), 3) for c, p in zip(classes, probs)},
            "backbone": bundle["backbone"], "version": bundle["version"]}
