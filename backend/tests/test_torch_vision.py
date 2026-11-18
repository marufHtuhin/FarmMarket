"""Tests for the PyTorch vision path (ai_services/computer_vision + torch_vision).

Torch-dependent tests skip cleanly when torch is not installed (importorskip);
the wrapper/status/503 tests run in both cases, so this file must PASS with
and without torch. Synthetic images only -- nothing here is evidence of
real-world accuracy.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root: ai_services

from conftest import fruit_image, register
from app.services import torch_vision as TV
from app.services import vision as V

TRAINED_AT = "2026-11-15T00:00:00Z"
COLOURS = {"class_a": (200, 40, 35), "class_b": (70, 150, 60), "class_c": (30, 90, 200)}


def _cv():
    """Import the torch pipeline modules (skips the test when torch is absent)."""
    pytest.importorskip("torch")
    from ai_services.computer_vision import dataset as cv_ds
    from ai_services.computer_vision import evaluate as cv_eval
    from ai_services.computer_vision import model as cv_model
    from ai_services.computer_vision import train as cv_train
    return cv_ds, cv_eval, cv_model, cv_train


def _write_images(tree: dict[str, dict[str, int]], root: Path) -> None:
    """tree: {split-or-"": {class: n_images}} of solid-colour synthetic JPEGs."""
    for split, classes in tree.items():
        for cls, n in classes.items():
            d = root / split / cls if split else root / cls
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                Image.new("RGB", (64, 64), COLOURS.get(cls, (120, 120, 120))).save(d / f"{i}.jpg")


def _make_torch_checkpoint(model_dir: Path, task: str, classes: list[str],
                           backbone: str = "mobilenet_v3_small") -> Path:
    """Random-init checkpoint + config.json under model_dir/torch/<task>/.

    mobilenet_v3_small by default: its checkpoint is ~6 MB vs ~44 MB for
    resnet18, which matters on the 512 MB /tmp tmpfs pytest uses.
    """
    _, _, cv_model, _ = _cv()
    out = model_dir / "torch" / task
    model = cv_model.build_model(backbone, len(classes), pretrained=False)
    cv_model.save_checkpoint(out / "best.pt", model, backbone, classes, task, {"task": task})
    (out / "config.json").write_text(json.dumps(
        {"task": task, "backbone": backbone, "classes": classes,
         "trained_at": TRAINED_AT, "best_val_acc": 0.5}))
    return out / "best.pt"


@pytest.fixture(autouse=True)
def _clear_caches():
    TV.clear_cache()
    V._cache.clear()
    yield
    TV.clear_cache()
    V._cache.clear()


# ---------------- dataset loaders (torch) ----------------

def test_dataset_loader_split_tree_balanced_sampler(tmp_path):
    cv_ds, _, _, _ = _cv()
    from torch.utils.data import WeightedRandomSampler
    _write_images({"train": {"class_a": 10, "class_b": 4}, "val": {"class_a": 3, "class_b": 2}},
                  tmp_path)
    loaders = cv_ds.build_loaders(tmp_path, "disease", batch_size=4, seed=0)
    assert loaders.classes == ["class_a", "class_b"]
    assert loaders.n_train == 14 and loaders.n_val == 5
    assert isinstance(loaders.train.sampler, WeightedRandomSampler)
    xb, yb = next(iter(loaders.train))
    assert xb.shape == (4, 3, 224, 224) and yb.shape == (4,)


def test_dataset_loader_flat_tree_stratified_split(tmp_path):
    cv_ds, _, _, _ = _cv()
    _write_images({"": {"class_a": 10, "class_b": 10}}, tmp_path)
    loaders = cv_ds.build_loaders(tmp_path, "disease", batch_size=4, val_split=0.2, seed=0)
    assert loaders.n_train == 16 and loaders.n_val == 4  # 2 val images per class: stratified
    assert loaders.classes == ["class_a", "class_b"]


def test_validate_layout_errors(tmp_path):
    cv_ds, _, _, _ = _cv()
    with pytest.raises(cv_ds.DatasetLayoutError):
        cv_ds.validate_layout(tmp_path / "missing", "disease")
    with pytest.raises(cv_ds.DatasetLayoutError):
        cv_ds.validate_layout(tmp_path, "disease")  # empty
    _write_images({"": {"class_a": 3}}, tmp_path)
    with pytest.raises(cv_ds.DatasetLayoutError, match="at least 2 classes"):
        cv_ds.validate_layout(tmp_path, "disease")
    _write_images({"": {"green": 3, "ripe": 3}}, tmp_path / "ripe")
    with pytest.raises(cv_ds.DatasetLayoutError, match="Ripeness folders must be named"):
        cv_ds.validate_layout(tmp_path / "ripe", "ripeness")


# ---------------- model.py (torch) ----------------

def test_build_model_output_size():
    _, _, cv_model, _ = _cv()
    import torch
    for backbone in ("resnet18", "mobilenet_v3_small"):
        m = cv_model.build_model(backbone, 3, pretrained=False)
        assert m(torch.zeros(1, 3, 224, 224)).shape == (1, 3)
    with pytest.raises(ValueError):
        cv_model.build_model("vgg16", 2, pretrained=False)


# ---------------- torch_vision wrapper (with AND without torch) ----------------

def test_torch_vision_no_checkpoint_returns_none(tmp_path):
    assert TV.load_torch_model("ripeness", tmp_path) is None
    assert TV.predict_torch("ripeness", fruit_image("ripe", np.random.default_rng(0)), tmp_path) is None
    assert TV.torch_model_version("ripeness", tmp_path) is None
    assert isinstance(TV.torch_available(), bool)


def test_torch_vision_checkpoint_without_torch(monkeypatch, tmp_path):
    """Checkpoint present but torch missing: predict raises a clear error,
    load returns None (never raises for an unavailable model)."""
    out = tmp_path / "torch" / "ripeness"
    out.mkdir(parents=True)
    (out / "best.pt").write_bytes(b"fake checkpoint")
    (out / "config.json").write_text(json.dumps({"backbone": "resnet18", "trained_at": TRAINED_AT}))
    monkeypatch.setattr(TV, "torch_available", lambda: False)
    assert TV.load_torch_model("ripeness", tmp_path) is None
    with pytest.raises(TV.TorchNotInstalledError):
        TV.predict_torch("ripeness", fruit_image("ripe", np.random.default_rng(0)), tmp_path)
    # Status versioning needs no torch at all.
    assert TV.torch_model_version("ripeness", tmp_path) == f"resnet18@{TRAINED_AT}"


def test_torch_vision_preprocess_matches_val_transforms():
    _cv()
    pytest.importorskip("torchvision")
    import io
    import torch
    from ai_services.computer_vision import dataset as cv_ds
    data = fruit_image("ripe", np.random.default_rng(0))
    a = TV._preprocess(data)
    b = cv_ds.val_transforms()(Image.open(io.BytesIO(data)).convert("RGB"))
    assert torch.allclose(a, b, atol=1e-6)


def test_predict_torch_with_checkpoint(tmp_path):
    _cv()
    _make_torch_checkpoint(tmp_path, "ripeness", ["unripe", "ripe"])
    pred = TV.predict_torch("ripeness", fruit_image("ripe", np.random.default_rng(0)), tmp_path)
    assert pred is not None
    assert pred["label"] in ("unripe", "ripe")
    assert pred["backbone"] == "mobilenet_v3_small" and pred["version"] == TRAINED_AT
    assert 0.0 <= pred["confidence"] <= 1.0
    assert set(pred["per_class"]) == {"unripe", "ripe"}
    assert abs(sum(pred["per_class"].values()) - 1.0) < 0.01
    assert TV.torch_model_version("ripeness", tmp_path) == f"mobilenet_v3_small@{TRAINED_AT}"


# ---------------- assess() backend selection (torch) ----------------

def test_assess_torch_only_degrades_gracefully(tmp_path):
    _cv()
    _make_torch_checkpoint(tmp_path, "ripeness", ["unripe", "ripe"])
    r = V.assess(fruit_image("ripe", np.random.default_rng(0)), None, tmp_path)
    assert r["model"] == {"ripeness": "torch-mobilenet_v3_small", "disease": "unavailable"}
    assert r["ripeness"] in ("unripe", "ripe")
    assert r["disease"] is None and r["notes"] == {"disease": "model_not_trained"}
    assert r["grade"] in ("A", "B", "C", "REVIEW")
    assert any("PyTorch model" in w for w in r["warnings"])
    assert any("disease" in w for w in r["warnings"])


def test_assess_mixed_backends(tmp_path):
    _cv()
    _make_torch_checkpoint(tmp_path, "ripeness", ["unripe", "ripe"], backbone="resnet18")
    rng = np.random.default_rng(0)
    V.train_classifier([(fruit_image("ripe", rng), "Tomato___healthy") for _ in range(20)]
                       + [(fruit_image("ripe", rng, True), "Tomato___Early_blight") for _ in range(20)],
                       "disease", tmp_path)
    r = V.assess(fruit_image("ripe", np.random.default_rng(1)), "tomato", tmp_path)
    assert r["model"] == {"ripeness": "torch-resnet18", "disease": "sklearn-randomforest"}
    assert r["notes"] == {}
    assert r["disease"] in ("Tomato___healthy", "Tomato___Early_blight")


def test_assess_corrupt_torch_checkpoint_falls_back_to_sklearn(tmp_path):
    _cv()
    out = tmp_path / "torch" / "ripeness"
    out.mkdir(parents=True)
    (out / "best.pt").write_bytes(b"not a checkpoint")
    (out / "config.json").write_text(json.dumps({"backbone": "resnet18", "trained_at": TRAINED_AT}))
    rng = np.random.default_rng(0)
    V.train_classifier([(fruit_image(k, rng), k) for k in V.RIPENESS_CLASSES for _ in range(20)],
                       "ripeness", tmp_path)
    r = V.assess(fruit_image("ripe", np.random.default_rng(1)), None, tmp_path)
    assert r["model"]["ripeness"] == "sklearn-randomforest"
    assert any("failed to load" in w for w in r["warnings"])


# ---------------- train.py / evaluate.py (torch) ----------------

def test_train_one_epoch_smoke(tmp_path):
    _, _, _, cv_train = _cv()
    data = tmp_path / "data"
    _write_images({"train": {"class_a": 4, "class_b": 4}, "val": {"class_a": 2, "class_b": 2}}, data)
    out = tmp_path / "out"
    args = argparse.Namespace(data=str(data), task="disease", backbone="mobilenet_v3_small", epochs=1,
                              batch_size=4, lr=1e-3, out=str(out), val_split=0.2, seed=0,
                              num_workers=0, no_pretrained=True, patience=3)
    cfg = cv_train.train(args)
    assert (out / "best.pt").exists() and (out / "config.json").exists()
    history = json.loads((out / "history.json").read_text())
    assert len(history) == 1 and {"train_loss", "val_loss", "val_acc"} <= set(history[0])
    assert cfg["best_val_acc"] == history[0]["val_acc"]


def test_evaluate_synthetic_checkpoint(tmp_path):
    _, cv_eval, _, _ = _cv()
    data = tmp_path / "data"
    _write_images({"train": {"class_a": 4, "class_b": 4}, "val": {"class_a": 2, "class_b": 2}}, data)
    ckpt = _make_torch_checkpoint(tmp_path, "disease", ["class_a", "class_b"])
    args = argparse.Namespace(checkpoint=str(ckpt), data=str(data), split="val",
                              batch_size=4, out=None)
    result = cv_eval.evaluate(args)
    assert result["n_images"] == 4 and result["classes"] == ["class_a", "class_b"]
    assert set(result["per_class"]) == {"class_a", "class_b"}
    assert all({"precision", "recall", "f1-score", "support"} <= set(m)
               for m in result["per_class"].values())
    assert len(result["confusion_matrix"]) == 2 and "accuracy" in result


# ---------------- API: status + 503 (with AND without torch) ----------------

def test_status_endpoint_reports_both_backends(client, tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    body = client.get("/api/v1/vision/status").json()
    assert body["torch_installed"] == TV.torch_available()
    assert body["torch_models"] == {"ripeness": None, "disease": None}
    assert body["sklearn_models"] == body["models"] == {"ripeness": None, "disease": None}
    assert body["grade_table"] == V.GRADE_TABLE and body["min_confidence"] == V.MIN_CONFIDENCE


def test_status_endpoint_reports_torch_version(client, tmp_path, monkeypatch):
    _cv()
    _make_torch_checkpoint(tmp_path, "ripeness", ["unripe", "ripe"])
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    body = client.get("/api/v1/vision/status").json()
    assert body["torch_models"] == {"ripeness": f"mobilenet_v3_small@{TRAINED_AT}", "disease": None}


def test_assess_api_503_when_no_model_at_all(client, tmp_path, monkeypatch):
    """API-level 503 (service-level 503 is covered in test_vision.py)."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    farmer = register(client, "f@x.t", "farmer")
    img = ("a.png", fruit_image("ripe", np.random.default_rng(1)), "image/png")
    assert client.post("/api/v1/vision/assess", files={"image": img}, headers=farmer).status_code == 503
