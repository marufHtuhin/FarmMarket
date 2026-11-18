"""PyTorch transfer-learning pipeline for fruit vision (disease + ripeness).

CPU-only by design: no GPU is assumed anywhere in this package.

  * model.py    - pretrained backbones (resnet18 / mobilenet_v3_small) with a
                  replaced classifier head, plus checkpoint save/load.
  * dataset.py  - ImageFolder loaders for PlantVillage-style disease folders
                  and ripeness folders, with class balancing.
  * train.py    - CLI trainer (AdamW, cosine schedule, early stopping).
  * evaluate.py - CLI evaluator (per-class precision/recall/F1, confusion
                  matrix).

NO trained model ships with this repo. Train your own from labelled photos
(see README.md) and place checkpoints under MODEL_DIR/torch/<task>/.
"""
