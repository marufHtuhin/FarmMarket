"""Train the ripeness and/or disease classifiers from image folders.

  # Disease (PlantVillage layout: <root>/Tomato___Early_blight/*.jpg, ...)
  python scripts/train_vision.py --disease /data/PlantVillage --max-per-class 400
  # Ripeness (YOUR OWN labelled folders: <root>/unripe|ripe|overripe/*.jpg)
  python scripts/train_vision.py --ripeness /data/ripeness
PlantVillage has no ripeness labels. Hold out field photos from your target region to test real accuracy:
PlantVillage images are lab-background shots and models trained on them degrade on farm photos.
"""
import _bootstrap  # noqa: F401
import argparse, json
from app.services.datasources.plantvillage import index_folder_dataset
from app.services import vision as V

ap = argparse.ArgumentParser()
ap.add_argument("--disease"); ap.add_argument("--ripeness"); ap.add_argument("--max-per-class", type=int, default=400)
a = ap.parse_args()
if not (a.disease or a.ripeness):
    raise SystemExit("Pass --disease and/or --ripeness")
for task, root in (("disease", a.disease), ("ripeness", a.ripeness)):
    if not root:
        continue
    samples = index_folder_dataset(root, a.max_per_class)
    if task == "ripeness":
        unknown = {l for _, l in samples} - set(V.RIPENESS_CLASSES)
        if unknown:
            raise SystemExit(f"Ripeness folders must be named {V.RIPENESS_CLASSES}; found extra: {sorted(unknown)}")
    rep = V.train_classifier([(str(p), l) for p, l in samples], task, dataset_note=f"{root} (max {a.max_per_class}/class)")
    print(task, json.dumps({k: v for k, v in rep.__dict__.items() if k != "confusion"}, indent=1))
