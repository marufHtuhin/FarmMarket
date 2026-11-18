"""Transfer-learning backbones + checkpoint save/load for FarmMarket vision.

Backbones are torchvision pretrained models with the classifier head replaced
for the task's class count. Everything runs on CPU; no GPU is assumed.

Checkpoint format (torch.save of a plain dict):
    {"state_dict": ..., "backbone": "resnet18", "classes": [...],
     "task": "disease" | "ripeness", "config": {...}}

Checkpoints live at MODEL_DIR/torch/<task>/best.pt next to a config.json
written by train.py. The backend service (app/services/torch_vision.py)
reads them; it never imports this module, so the API stays torch-free.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import torch
from torch import nn
from torchvision import models

BACKBONES = ("resnet18", "mobilenet_v3_small")


def build_model(backbone: str = "resnet18", num_classes: int = 2,
                pretrained: bool = True) -> nn.Module:
    """Pretrained backbone with a fresh classifier head for `num_classes`.

    `pretrained=False` skips the ImageNet weight download (random init) --
    useful for smoke tests and for offline environments.
    """
    if backbone not in BACKBONES:
        raise ValueError(f"Unknown backbone {backbone!r}; choose from {BACKBONES}")
    if num_classes < 2:
        raise ValueError("num_classes must be >= 2")
    weights = "DEFAULT" if pretrained else None
    if backbone == "resnet18":
        model = models.resnet18(weights=weights)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    else:  # mobilenet_v3_small: classifier is a Sequential, last layer Linear
        model = models.mobilenet_v3_small(weights=weights)
        last = model.classifier[-1]
        model.classifier[-1] = nn.Linear(last.in_features, num_classes)
    return model


def save_checkpoint(path: str | Path, model: nn.Module, backbone: str,
                    classes: list[str], task: str,
                    config: dict[str, Any] | None = None) -> Path:
    """Save {state_dict, backbone, classes, task, config} via torch.save."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"state_dict": model.state_dict(), "backbone": backbone,
               "classes": list(classes), "task": task, "config": dict(config or {})}
    torch.save(payload, path)
    return path


def load_checkpoint(path: str | Path, device: str = "cpu") -> tuple[nn.Module, dict[str, Any]]:
    """Load a checkpoint saved by save_checkpoint(); returns (model, meta).

    `meta` is the checkpoint dict minus the state dict. Raises ValueError on
    a malformed checkpoint instead of failing obscurely inside torch.load.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {path}")
    payload = torch.load(path, map_location=device, weights_only=True)
    for key in ("state_dict", "backbone", "classes", "task"):
        if key not in payload:
            raise ValueError(f"Checkpoint {path} is missing {key!r}; "
                             "was it saved by ai_services.computer_vision.model.save_checkpoint?")
    model = build_model(payload["backbone"], len(payload["classes"]), pretrained=False)
    model.load_state_dict(payload["state_dict"])
    model.eval()
    meta = {k: v for k, v in payload.items() if k != "state_dict"}
    return model, meta
