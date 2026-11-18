"""Train a FarmMarket vision classifier (disease or ripeness) with PyTorch.

CPU-only transfer learning: a pretrained torchvision backbone with a fresh
classifier head, AdamW + CrossEntropyLoss, cosine LR schedule, early stopping
(patience 3), best-checkpoint saving by validation accuracy.

Usage (from the repo root):
    python -m ai_services.computer_vision.train --data data/plantvillage \\
        --task disease --backbone resnet18 --epochs 10 \\
        --out backend/models/torch/disease
    python -m ai_services.computer_vision.train --data data/ripeness \\
        --task ripeness --epochs 10 --out backend/models/torch/ripeness

Outputs in --out: best.pt + last.pt (checkpoints), config.json, history.json
(per-epoch train_loss / val_loss / val_acc). Fails loudly (non-zero exit)
on a bad data layout. Also runnable as a script: python train.py ...
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running both as `python -m ai_services.computer_vision.train` from the
# repo root and as `python train.py` from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import torch
from torch import nn

from ai_services.computer_vision import dataset as ds
from ai_services.computer_vision.model import BACKBONES, build_model, save_checkpoint


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train a FarmMarket vision classifier.")
    p.add_argument("--data", required=True, help="Dataset root (split or flat layout, see README)")
    p.add_argument("--task", required=True, choices=["disease", "ripeness"])
    p.add_argument("--backbone", default="resnet18", choices=BACKBONES)
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--out", required=True, help="Output dir for best.pt, config.json, history.json")
    p.add_argument("--val-split", type=float, default=0.2,
                   help="Validation fraction when --data is a flat class tree (ignored with train/val splits)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--num-workers", type=int, default=0)
    p.add_argument("--no-pretrained", action="store_true",
                   help="Random init instead of ImageNet weights (offline / smoke tests)")
    p.add_argument("--patience", type=int, default=3, help="Early-stopping patience (epochs)")
    return p.parse_args(argv)


def _run_epoch(model: nn.Module, loader, criterion, optimizer, device: str,
               train: bool) -> tuple[float, float]:
    model.train(train)
    total_loss, correct, n = 0.0, 0, 0
    ctx = torch.enable_grad() if train else torch.no_grad()
    with ctx:
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            if train:
                optimizer.zero_grad()
            out = model(images)
            loss = criterion(out, labels)
            if train:
                loss.backward()
                optimizer.step()
            total_loss += loss.item() * len(labels)
            correct += int((out.argmax(1) == labels).sum())
            n += len(labels)
    return total_loss / max(n, 1), correct / max(n, 1)


def train(args: argparse.Namespace) -> dict:
    torch.manual_seed(args.seed)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = "cpu"  # CPU-only by design; no GPU assumed.
    print(f"[train] task={args.task} backbone={args.backbone} data={args.data} device={device}")
    try:
        loaders = ds.build_loaders(args.data, args.task, batch_size=args.batch_size,
                                   val_split=args.val_split, seed=args.seed,
                                   num_workers=args.num_workers)
    except ds.DatasetLayoutError as e:
        raise SystemExit(f"[train] ERROR: {e}") from e
    print(f"[train] classes ({len(loaders.classes)}): {loaders.classes}")
    print(f"[train] train={loaders.n_train} images, val={loaders.n_val} images")
    model = build_model(args.backbone, len(loaders.classes), pretrained=not args.no_pretrained)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    config = {"task": args.task, "backbone": args.backbone, "classes": loaders.classes,
              "num_classes": len(loaders.classes), "epochs": args.epochs,
              "batch_size": args.batch_size, "lr": args.lr, "seed": args.seed,
              "val_split": args.val_split, "image_size": ds.IMAGE_SIZE,
              "data": str(args.data), "pretrained": not args.no_pretrained,
              "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")}
    history: list[dict] = []
    best_acc, best_epoch, since_best = -1.0, -1, 0
    t0 = time.time()
    for epoch in range(1, args.epochs + 1):
        tr_loss, tr_acc = _run_epoch(model, loaders.train, criterion, optimizer, device, train=True)
        va_loss, va_acc = _run_epoch(model, loaders.val, criterion, optimizer, device, train=False)
        scheduler.step()
        history.append({"epoch": epoch, "train_loss": round(tr_loss, 4), "train_acc": round(tr_acc, 4),
                        "val_loss": round(va_loss, 4), "val_acc": round(va_acc, 4)})
        print(f"[train] epoch {epoch}/{args.epochs} train_loss={tr_loss:.4f} train_acc={tr_acc:.3f} "
              f"val_loss={va_loss:.4f} val_acc={va_acc:.3f}")
        save_checkpoint(out_dir / "last.pt", model, args.backbone, loaders.classes, args.task, config)
        if va_acc > best_acc:
            best_acc, best_epoch, since_best = va_acc, epoch, 0
            config["best_val_acc"] = round(best_acc, 4)
            config["best_epoch"] = best_epoch
            save_checkpoint(out_dir / "best.pt", model, args.backbone, loaders.classes, args.task, config)
            print(f"[train] new best val_acc={best_acc:.3f} -> best.pt")
        else:
            since_best += 1
            if since_best >= args.patience:
                print(f"[train] early stopping: no val improvement for {args.patience} epochs")
                break
    config["n_train"], config["n_val"] = loaders.n_train, loaders.n_val
    config["seconds"] = round(time.time() - t0, 1)
    (out_dir / "config.json").write_text(json.dumps(config, indent=2))
    (out_dir / "history.json").write_text(json.dumps(history, indent=2))
    print(f"[train] done in {config['seconds']}s; best val_acc={best_acc:.3f} (epoch {best_epoch}); "
          f"checkpoints in {out_dir}")
    return config


def main(argv: list[str] | None = None) -> dict:
    return train(parse_args(argv))


if __name__ == "__main__":
    main()
