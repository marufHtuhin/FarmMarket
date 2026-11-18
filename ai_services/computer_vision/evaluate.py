"""Evaluate a trained FarmMarket vision checkpoint.

Usage (from the repo root):
    python -m ai_services.computer_vision.evaluate \\
        --checkpoint backend/models/torch/disease/best.pt \\
        --data data/plantvillage --split val --out eval_disease.json

Reports per-class precision / recall / F1 and the confusion matrix (sklearn
metrics) as JSON on stdout (and to --out when given), plus a readable console
table. Accuracy is NEVER printed without the number of evaluated images and
the class list -- a bare accuracy number on a small or skewed set misleads.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running both as a module and as a script (see train.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from ai_services.computer_vision import dataset as ds
from ai_services.computer_vision.model import load_checkpoint


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate a FarmMarket vision checkpoint.")
    p.add_argument("--checkpoint", required=True, help="Path to best.pt / last.pt")
    p.add_argument("--data", required=True, help="Dataset root (split or flat layout)")
    p.add_argument("--split", default="val", help="Split folder to evaluate (default: val)")
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--out", help="Optional path to write the JSON report")
    return p.parse_args(argv)


def evaluate(args: argparse.Namespace) -> dict:
    model, meta = load_checkpoint(args.checkpoint)
    classes = meta["classes"]
    try:
        loader, found = ds.build_eval_loader(args.data, args.split, batch_size=args.batch_size)
    except ds.DatasetLayoutError as e:
        raise SystemExit(f"[evaluate] ERROR: {e}") from e
    if found != classes:
        raise SystemExit(f"[evaluate] ERROR: checkpoint classes {classes} do not match "
                         f"dataset classes {found}")
    y_true, y_pred = [], []
    with torch.no_grad():
        for images, labels in loader:
            y_pred += model(images).argmax(1).tolist()
            y_true += labels.tolist()
    report = classification_report(y_true, y_pred, labels=list(range(len(classes))),
                                   target_names=classes, output_dict=True, zero_division=0)
    per_class = {c: {k: round(v, 4) for k, v in report[c].items() if k in
                     ("precision", "recall", "f1-score", "support")} for c in classes}
    result = {"checkpoint": str(args.checkpoint), "task": meta.get("task"),
              "backbone": meta.get("backbone"), "split": args.split,
              "n_images": len(y_true), "classes": classes,
              "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
              "macro_f1": round(float(report["macro avg"]["f1-score"]), 4),
              "per_class": per_class,
              "confusion_matrix": confusion_matrix(y_true, y_pred,
                                                   labels=list(range(len(classes)))).tolist()}
    # Console table -- accuracy always shown together with n_images + classes.
    print(f"checkpoint: {args.checkpoint} (task={result['task']}, backbone={result['backbone']})")
    print(f"split={args.split}  n_images={result['n_images']}  classes={classes}")
    print(f"accuracy={result['accuracy']:.4f}  macro_f1={result['macro_f1']:.4f}")
    print(f"{'class':<28} {'precision':>9} {'recall':>7} {'f1':>7} {'support':>7}")
    for c in classes:
        m = per_class[c]
        print(f"{c:<28} {m['precision']:>9.3f} {m['recall']:>7.3f} {m['f1-score']:>7.3f} {int(m['support']):>7}")
    print("confusion matrix (rows=true, cols=predicted):")
    for row in result["confusion_matrix"]:
        print("  " + " ".join(f"{v:>4}" for v in row))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2))
        print(f"JSON report written to {args.out}")
    return result


def main(argv: list[str] | None = None) -> dict:
    args = parse_args(argv)
    result = evaluate(args)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
