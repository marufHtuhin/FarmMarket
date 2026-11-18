import numpy as np
import pytest
from pathlib import Path
from conftest import fruit_image
from app.services import vision as V


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    """Plumbing check on crude synthetic images - NOT evidence of real-world accuracy."""
    rng = np.random.default_rng(0)
    out = tmp_path_factory.mktemp("models")
    V.train_classifier([(fruit_image(k, rng), k) for k in V.RIPENESS_CLASSES for _ in range(40)], "ripeness", out)
    dis = ([(fruit_image("ripe", rng), "Tomato___healthy") for _ in range(50)]
           + [(fruit_image("ripe", rng, spots=True), "Tomato___Early_blight") for _ in range(50)])
    V.train_classifier(dis, "disease", out)
    return out


def test_features_are_fixed_length_and_finite():
    rng = np.random.default_rng(1)
    a = V.extract_features(V.load_image(fruit_image("ripe", rng)))
    b = V.extract_features(V.load_image(fruit_image("unripe", rng)))
    assert a.shape == b.shape and np.isfinite(a).all()


def test_training_writes_model_card(trained):
    assert (trained / "ripeness.joblib").exists() and (trained / "ripeness.card.json").exists()


def test_assess_ripe_healthy_is_grade_a(trained):
    rng = np.random.default_rng(5)
    r = V.assess(fruit_image("ripe", rng), "tomato", trained)
    assert r["ripeness"] == "ripe" and r["grade"] == "A" and r["price_multiplier"] == 1.0
    assert V.suggest_price(100, r["price_multiplier"]) == 100.0


def test_assess_diseased_is_not_graded_a(trained):
    rng = np.random.default_rng(6)
    r = V.assess(fruit_image("ripe", rng, spots=True), "tomato", trained)
    assert r["grade"] in ("C", "REVIEW")


def test_crop_mismatch_forces_manual_review(trained):
    rng = np.random.default_rng(7)
    r = V.assess(fruit_image("ripe", rng), "banana", trained)
    assert r["grade"] == "REVIEW" and r["price_multiplier"] is None and r["needs_manual_review"]


def test_grade_rules_and_low_confidence():
    assert V.grade("ripe", 0.9, "Tomato___healthy", 0.9)["grade"] == "A"
    assert V.grade("unripe", 0.9, "Tomato___healthy", 0.9)["grade"] == "B"
    assert V.grade("overripe", 0.9, "Tomato___healthy", 0.9)["grade"] == "C"
    assert V.grade("ripe", 0.9, "Tomato___Late_blight", 0.9)["grade"] == "C"
    low = V.grade("ripe", 0.9, "Tomato___healthy", 0.4)
    assert low["grade"] == "REVIEW" and low["price_multiplier"] is None
    assert V.suggest_price(50, None) is None


def test_missing_model_is_an_error_not_a_guess(tmp_path):
    with pytest.raises(V.ModelNotAvailableError):
        V.assess(fruit_image("ripe", np.random.default_rng(0)), None, tmp_path)


def test_bad_and_oversized_images_rejected():
    with pytest.raises(V.BadImageError):
        V.load_image(b"not an image")
    with pytest.raises(V.BadImageError):
        V.load_image(b"0" * (V.MAX_IMAGE_BYTES + 1))
