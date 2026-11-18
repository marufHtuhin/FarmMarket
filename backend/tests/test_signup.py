"""Signup improvements (18 Nov 2026): any 6+ character password is accepted
(no letter/digit complexity rule — there never was one in code; the old
backend minimum of 8 disagreed with the frontend's 6, so a 6-digit password
passed the form and then failed with a cryptic 422), and district/upazila
from the 64-district selects persist on the user.

District is required by the FRONTEND form only. The API keeps it optional
(default "") so existing API clients and older users without a district
keep working.
"""
from conftest import register
from app import models


def _register(client, email, password, **extra):
    body = {"name": "Test User", "email": email,
            "password": password, "role": "farmer"}
    body.update(extra)
    return client.post("/api/v1/auth/register", json=body)


# ---------------- password policy: min 6, any characters ----------------
def test_digits_only_6_char_password_registers_and_logs_in(client):
    r = _register(client, "digits@x.t", "123456")
    assert r.status_code == 200
    login = client.post("/api/v1/auth/login",
                        json={"email": "digits@x.t", "password": "123456"})
    assert login.status_code == 200


def test_letters_only_6_char_password_registers(client):
    r = _register(client, "letters@x.t", "abcdef")
    assert r.status_code == 200


def test_5_char_password_rejected_422(client):
    r = _register(client, "short@x.t", "12345")
    assert r.status_code == 422


def test_reset_password_accepts_digits_only_6_chars(client):
    register(client, "f@x.t", "farmer")
    token = client.post("/api/v1/auth/forgot-password",
                        json={"email": "f@x.t"}).json()["reset_token"]
    r = client.post("/api/v1/auth/reset-password",
                    json={"token": token, "new_password": "654321"})
    assert r.status_code == 200
    login = client.post("/api/v1/auth/login",
                        json={"email": "f@x.t", "password": "654321"})
    assert login.status_code == 200


# ---------------- district / upazila persistence ----------------
def test_register_with_district_and_upazila_persists_both(client, db):
    r = _register(client, "loc@x.t", "Passw0rd!",
                  district="Dhaka", upazila="Savar")
    assert r.status_code == 200
    assert r.json()["user"]["district"] == "Dhaka"
    assert r.json()["user"]["upazila"] == "Savar"
    user = db.query(models.User).filter_by(email="loc@x.t").first()
    assert user.district == "Dhaka" and user.upazila == "Savar"


def test_register_with_district_only_works(client, db):
    r = _register(client, "donly@x.t", "Passw0rd!", district="Khulna")
    assert r.status_code == 200
    assert r.json()["user"]["district"] == "Khulna"
    assert r.json()["user"]["upazila"] == ""
    user = db.query(models.User).filter_by(email="donly@x.t").first()
    assert user.district == "Khulna" and user.upazila == ""


def test_register_without_district_still_works(client, db):
    # API keeps district optional: old clients and pre-select users work.
    r = _register(client, "nodist@x.t", "Passw0rd!")
    assert r.status_code == 200
    user = db.query(models.User).filter_by(email="nodist@x.t").first()
    assert user.district == "" and user.upazila == ""
