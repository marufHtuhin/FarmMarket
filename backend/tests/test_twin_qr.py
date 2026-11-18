"""Digital Twin QR codes + sensor alerts tests (Phase 7)."""
from datetime import datetime, timedelta

from conftest import register
from app import models
from app.security import create_access_token

T0 = datetime(2026, 11, 2, 12, 0)


def make_batch(client, headers, crop="tomato"):
    r = client.post("/api/v1/twin/batches",
                    json={"crop": crop, "origin_district": "Gazipur", "quantity_kg": 100},
                    headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["batch_code"]


def add_reading(db, code, temp=None, rh=None, kind="rh", minutes=0):
    batch = db.query(models.Batch).filter_by(batch_code=code).one()
    r = models.SensorReading(batch_id=batch.id, device_id="DEV-TEST",
                             recorded_at=T0 + timedelta(minutes=minutes),
                             temperature_c=temp, moisture_pct=rh, moisture_kind=kind,
                             signature=f"test-{batch.id}-{minutes}-{temp}-{rh}")
    db.add(r)
    db.commit()
    return r


def test_qr_returns_png(client, db):
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store"
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")   # PNG magic bytes
    # Floor is 200, not 500: the encoded URL is now the (short) request host
    # when PUBLIC_BASE_URL is unset, so the QR PNG is smaller (~451 bytes).
    assert len(r.content) > 200


def test_qr_unknown_code_404(client, db):
    assert client.get("/api/v1/twin/batches/FM-NOPE/qr").status_code == 404


def test_qr_needs_no_login(client, db):
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    assert client.get(f"/api/v1/twin/batches/{code}/qr").status_code == 200


def test_public_view_includes_qr_url(client, db):
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/public/{code}")
    assert r.status_code == 200
    assert r.json()["qr_url"] == f"/api/v1/twin/batches/{code}/qr"
    assert r.json()["batch_code"] == code   # existing fields unchanged


def test_alerts_flag_out_of_range_reading(client, db):
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h, crop="tomato")   # tomato range 8-15 C, RH 85-95%
    add_reading(db, code, temp=45.0, rh=90.0)
    r = client.get(f"/api/v1/twin/batches/{code}/alerts", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["alerts"]) >= 1
    temp_alerts = [a for a in body["alerts"] if a["metric"] == "temperature_c"]
    assert temp_alerts and temp_alerts[0]["value"] == 45.0
    assert temp_alerts[0]["threshold"] == {"min": 8.0, "max": 15.0}
    assert temp_alerts[0]["severity"] in ("warning", "critical")
    assert body["thresholds"]["temperature_c"] == {"min": 8.0, "max": 15.0}


def test_alerts_none_for_in_range_readings(client, db):
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h, crop="tomato")
    add_reading(db, code, temp=12.0, rh=90.0)
    add_reading(db, code, temp=14.0, rh=88.0, minutes=30)
    r = client.get(f"/api/v1/twin/batches/{code}/alerts", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["alerts"] == []
    assert r.json()["n_readings"] == 2


def test_alerts_403_for_non_owner(client, db):
    h = register(client, "f@x.t", "farmer")
    other = register(client, "f2@x.t", "farmer")
    code = make_batch(client, h)
    assert client.get(f"/api/v1/twin/batches/{code}/alerts", headers=other).status_code == 403
    assert client.get(f"/api/v1/twin/batches/{code}/alerts").status_code == 401


def test_alerts_allowed_for_admin(client, db):
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    admin = models.User(name="Admin", email="a@x.t", password_hash="x", role="admin")
    db.add(admin)
    db.commit()
    ah = {"Authorization": "Bearer " + create_access_token(admin.id)}
    r = client.get(f"/api/v1/twin/batches/{code}/alerts", headers=ah)
    assert r.status_code == 200, r.text


def _capture_qr_data(monkeypatch):
    """Replace qrcode.QRCode with a fake that records the encoded URL.

    Returns a dict; the encoded URL lands in ``captured["url"]``. Decoding a
    real QR PNG would need an extra decoder dependency, so the fake records
    the exact string handed to add_data instead.
    """
    import qrcode
    captured = {}

    class FakeImage:
        def save(self, buf, format=None):
            buf.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 600)

    class FakeQRCode:
        def __init__(self, *a, **kw):
            pass

        def add_data(self, data):
            captured["url"] = data

        def make(self, fit=True):
            pass

        def make_image(self, fill_color=None, back_color=None):
            return FakeImage()

    monkeypatch.setattr(qrcode, "QRCode", FakeQRCode)
    return captured


def test_qr_uses_request_host_when_base_unset(client, db, monkeypatch):
    """No PUBLIC_BASE_URL: the QR encodes the host the client reached, never localhost."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr")
    assert r.status_code == 200
    assert captured["url"] == f"http://testserver/verify/{code}"
    assert "127.0.0.1" not in captured["url"]
    assert "localhost" not in captured["url"]


def test_qr_explicit_base_url_wins(client, db, monkeypatch):
    """An explicit PUBLIC_BASE_URL still wins over the request host (trailing slash stripped)."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://farm.example.com/")
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr")
    assert r.status_code == 200
    assert captured["url"] == f"https://farm.example.com/verify/{code}"


def test_qr_honors_forwarded_proto(client, db, monkeypatch):
    """Behind a TLS-terminating tunnel/proxy uvicorn sees plain http, so the
    QR must take its scheme from X-Forwarded-Proto — otherwise a phone
    scanning it gets an http:// URL for an https site."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "Host": "farm-5173.inc1.devtunnels.ms",
        "X-Forwarded-Proto": "https",
    })
    assert r.status_code == 200
    assert captured["url"] == f"https://farm-5173.inc1.devtunnels.ms/verify/{code}"


def test_qr_ignores_invalid_forwarded_proto(client, db, monkeypatch):
    """A bogus X-Forwarded-Proto value must not end up in the QR URL."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr",
                   headers={"X-Forwarded-Proto": "gopher"})
    assert r.status_code == 200
    assert captured["url"] == f"http://testserver/verify/{code}"


def test_qr_explicit_base_url_wins_over_forwarded_proto(client, db, monkeypatch):
    """PUBLIC_BASE_URL beats both the request host and X-Forwarded-Proto."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://farm.example.com")
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr",
                   headers={"X-Forwarded-Proto": "http"})
    assert r.status_code == 200
    assert captured["url"] == f"https://farm.example.com/verify/{code}"


def test_qr_uses_forwarded_host(client, db, monkeypatch):
    """Dev chain rewrites Host twice (devtunnel -> localhost, vite proxy ->
    127.0.0.1:8000), so the request host is always localhost in dev. The
    tunnel carries the public host in X-Forwarded-Host instead — the QR
    must use it (scheme from X-Forwarded-Proto)."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "Host": "127.0.0.1:8000",
        "X-Forwarded-Host": "farm-5173.inc1.devtunnels.ms",
        "X-Forwarded-Proto": "https",
    })
    assert r.status_code == 200
    assert captured["url"] == f"https://farm-5173.inc1.devtunnels.ms/verify/{code}"


def test_qr_forwarded_host_defaults_to_https(client, db, monkeypatch):
    """A forwarded host with no X-Forwarded-Proto is an https edge (devtunnel
    / Caddy / PaaS are all TLS-terminating), so the QR defaults to https."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "X-Forwarded-Host": "farm-5173.inc1.devtunnels.ms",
    })
    assert r.status_code == 200
    assert captured["url"] == f"https://farm-5173.inc1.devtunnels.ms/verify/{code}"


def test_qr_ignores_malformed_forwarded_host(client, db, monkeypatch):
    """A forwarded host containing path/@/query characters is not a host —
    ignore it and fall back to the request host."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "X-Forwarded-Host": "evil.com/verify/x",
    })
    assert r.status_code == 200
    assert captured["url"] == f"http://testserver/verify/{code}"


def test_qr_explicit_base_url_wins_over_forwarded_host(client, db, monkeypatch):
    """PUBLIC_BASE_URL beats X-Forwarded-Host too."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://farm.example.com")
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "X-Forwarded-Host": "farm-5173.inc1.devtunnels.ms",
        "X-Forwarded-Proto": "https",
    })
    assert r.status_code == 200
    assert captured["url"] == f"https://farm.example.com/verify/{code}"


def test_qr_uses_referer_origin(client, db, monkeypatch):
    """The devtunnel does NOT set X-Forwarded-Host (live finding), so the QR
    must take the public host from the Referer origin instead: the browser
    fetches the QR <img> same-origin and reports the page's real address.
    Only the origin is used — the Referer's path is discarded."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "Host": "127.0.0.1:8000",
        "Referer": f"https://farm-5173.inc1.devtunnels.ms/batches/{code}",
    })
    assert r.status_code == 200
    assert captured["url"] == f"https://farm-5173.inc1.devtunnels.ms/verify/{code}"


def test_qr_referer_localhost_is_localhost(client, db, monkeypatch):
    """A localhost Referer means the page really was opened via localhost,
    so the QR encoding localhost is correct there (e.g. local dev on the
    same machine)."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "Referer": "http://localhost:5173/batches/whatever",
    })
    assert r.status_code == 200
    assert captured["url"] == f"http://localhost:5173/verify/{code}"


def test_qr_ignores_malformed_referer(client, db, monkeypatch):
    """A malformed Referer (wrong scheme, userinfo, non-numeric port, or a
    host with illegal chars) is ignored and the resolver falls through to
    X-Forwarded-Host / the request host."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    bad_referers = [
        "javascript:alert(1)",
        "ftp://files.example.com/x",
        "https://evil.com@good.com/",
        "https://farm.example.com:badport/",
        "not-a-url",
    ]
    for bad in bad_referers:
        captured = _capture_qr_data(monkeypatch)
        r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={"Referer": bad})
        assert r.status_code == 200, bad
        assert captured["url"] == f"http://testserver/verify/{code}", bad


def test_qr_explicit_base_url_wins_over_referer(client, db, monkeypatch):
    """PUBLIC_BASE_URL still beats the Referer origin."""
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://farm.example.com")
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "Referer": "https://farm-5173.inc1.devtunnels.ms/batches/x",
    })
    assert r.status_code == 200
    assert captured["url"] == f"https://farm.example.com/verify/{code}"


def test_qr_referer_beats_forwarded_host(client, db, monkeypatch):
    """When both are present, the Referer origin wins over X-Forwarded-Host
    (the browser's report of the page address is the primary dynamic source)."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    r = client.get(f"/api/v1/twin/batches/{code}/qr", headers={
        "Referer": "https://farm-5173.inc1.devtunnels.ms/batches/x",
        "X-Forwarded-Host": "other.example.com",
        "X-Forwarded-Proto": "https",
    })
    assert r.status_code == 200
    assert captured["url"] == f"https://farm-5173.inc1.devtunnels.ms/verify/{code}"


def test_public_view_verify_url_matches_qr(client, db, monkeypatch):
    """GET /twin/public/{code} exposes verify_url — the exact URL the QR
    encodes, resolved by the same resolver — so the UI can show it."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    captured = _capture_qr_data(monkeypatch)
    h = register(client, "f@x.t", "farmer")
    code = make_batch(client, h)
    headers = {"Host": "127.0.0.1:8000",
               "Referer": f"https://farm-5173.inc1.devtunnels.ms/batches/{code}"}
    r = client.get(f"/api/v1/twin/public/{code}", headers=headers)
    assert r.status_code == 200
    assert r.json()["verify_url"] == f"https://farm-5173.inc1.devtunnels.ms/verify/{code}"
    qr = client.get(f"/api/v1/twin/batches/{code}/qr", headers=headers)
    assert qr.status_code == 200
    assert captured["url"] == r.json()["verify_url"]
