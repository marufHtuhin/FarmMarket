import os, tempfile
# conftest is executed TWICE per pytest process: once as top-level
# `conftest` (pytest's own import) and once as `tests.conftest` (test
# files do `from tests.conftest import ...`), because tests/ has no
# __init__.py. Without this guard the second execution makes a NEW tmp
# dir and re-points UPLOAD_DIR/DATABASE_URL at it — while the app (if
# already imported, e.g. by a test file's module-level
# `from app.main import ...`) still serves/mounts the FIRST dir. That
# mismatch made test_product_image_upload_and_validation 404: the file
# landed in the second tmp dir while /uploads served the first. The
# sentinel env var makes the second execution a no-op.
if "FM_TEST_TMP" not in os.environ:
    _tmp = tempfile.mkdtemp(prefix="fm_test_")
    os.environ["FM_TEST_TMP"] = _tmp
    os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
    os.environ["MODEL_DIR"] = f"{_tmp}/models"
    os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
    os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-0123"
    os.environ["ENVIRONMENT"] = "development"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("OPENWEATHER_API_KEY", None)

import io
import numpy as np
import pytest
from PIL import Image, ImageDraw


@pytest.fixture(scope="session")
def app_module():
    from app.main import app
    return app


@pytest.fixture()
def db():
    from app.database import Base, engine, SessionLocal
    from app.services.rate_limit import reset_auth_limiters
    reset_auth_limiters()  # module-level auth limiters must not leak between tests
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def client(app_module, db):
    from fastapi.testclient import TestClient
    return TestClient(app_module)


def register(client, email, role, district="Gazipur"):
    r = client.post("/api/v1/auth/register", json={"name": "User " + email.split("@")[0], "email": email,
                    "password": "Passw0rd!", "role": role, "district": district})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def fruit_image(kind: str, rng, spots: bool = False) -> bytes:
    """Crude synthetic 'fruit' used ONLY to exercise the training/inference plumbing."""
    bg = tuple(int(x) for x in rng.integers(200, 255, 3))
    img = Image.new("RGB", (160, 160), bg)
    d = ImageDraw.Draw(img)
    col = {"unripe": (70, 150, 60), "ripe": (200, 40, 35), "overripe": (110, 35, 30)}[kind]
    col = tuple(int(np.clip(c + rng.integers(-20, 20), 0, 255)) for c in col)
    d.ellipse((30, 30, 130, 130), fill=col)
    if spots:
        for _ in range(25):
            x, y = rng.integers(40, 115, 2)
            d.ellipse((x, y, x + 12, y + 12), fill=(55, 30, 15))
    arr = np.asarray(img).astype(int) + rng.integers(-8, 8, (160, 160, 3))
    out = io.BytesIO()
    Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).save(out, "PNG")
    return out.getvalue()
