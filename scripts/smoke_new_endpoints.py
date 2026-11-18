#!/usr/bin/env python3
"""Live smoke test for the new batch endpoints (messaging, weather,
manual prices, assistant test probe + streaming).

Usage: start the backend on a scratch seeded SQLite DB first, e.g.
  cd backend
  DATABASE_URL=sqlite:////tmp/smoke.db SECRET_KEY=smoke-secret-key \
    python seed_demo.py
  DATABASE_URL=sqlite:////tmp/smoke.db SECRET_KEY=smoke-secret-key \
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8107
then:  python scripts/smoke_new_endpoints.py [base_url]

Uses only the standard library. Exits non-zero if any check fails.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8107"

PASSED = 0
FAILED = 0


def check(name, cond, detail=""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  ok  {name}")
    else:
        FAILED += 1
        print(f"FAIL  {name}  {detail}")


def req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, {"_raw": raw}  # HTML (SPA) etc.
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"_raw": raw}
    except urllib.error.URLError as e:
        return 0, {"_error": str(e)}


def login(email):
    status, body = req("POST", "/api/v1/auth/login",
                       body={"email": email, "password": "Demo123!"})
    return status, body.get("access_token")


def main():
    # Health + SPA
    s, b = req("GET", "/api/health")
    check("health 200 + db ok", s == 200 and b.get("db") == "ok", f"{s} {b}")
    s, _ = req("GET", "/")
    check("SPA / serves 200", s == 200, f"{s}")
    s, _ = req("GET", "/weather")
    check("SPA fallback /weather serves 200", s == 200, f"{s}")

    # Weather (LIVE Open-Meteo, no key)
    s, b = req("GET", "/api/v1/weather/dhaka")
    check("weather dhaka live", s == 200 and b.get("available") is True
          and b.get("source") == "open-meteo"
          and len(b.get("past", [])) == 7
          and len(b.get("forecast", [])) == 8
          and isinstance(b.get("current", {}).get("temperature_c"),
                         (int, float)),
          f"{s} {str(b)[:200]}")
    s, _ = req("GET", "/api/v1/weather/nowhere")
    check("weather unknown hub 404", s == 404, f"{s}")

    # Logins (seeded demo users)
    s, farmer_tok = login("farmer@farmmarket.demo")
    check("farmer login", s == 200 and bool(farmer_tok), f"{s}")
    s, buyer_tok = login("buyer@farmmarket.demo")
    check("buyer login", s == 200 and bool(buyer_tok), f"{s}")
    s, admin_tok = login("admin@farmmarket.demo")
    check("admin login", s == 200 and bool(admin_tok), f"{s}")
    s, transp_tok = login("transporter@farmmarket.demo")
    check("transporter login", s == 200 and bool(transp_tok), f"{s}")
    s, me = req("GET", "/api/v1/auth/me", token=buyer_tok)
    buyer_id = me.get("id")
    check("buyer /auth/me has id", s == 200 and buyer_id, f"{s} {me}")

    # Messaging
    s, conv = req("POST", "/api/v1/conversations", token=farmer_tok,
                  body={"other_user_id": buyer_id})
    conv_id = conv.get("id")
    check("create conversation", s in (200, 201) and conv_id, f"{s} {conv}")
    s, msg = req("POST", f"/api/v1/conversations/{conv_id}/messages",
                 token=farmer_tok, body={"body": "Smoke test hello"})
    check("send message", s in (200, 201) and msg.get("body") == "Smoke test hello",
          f"{s} {msg}")
    s, msgs = req("GET", f"/api/v1/conversations/{conv_id}/messages",
                  token=buyer_tok)
    items = msgs if isinstance(msgs, list) else msgs.get("messages", [])
    check("buyer reads thread", s == 200 and any(
        m.get("body") == "Smoke test hello" for m in items), f"{s}")
    s, u = req("GET", "/api/v1/conversations/unread-count", token=buyer_tok)
    unread = u.get("unread") if isinstance(u, dict) else None
    if unread is None:
        unread = u.get("count") if isinstance(u, dict) else None
    check("buyer unread count is 1", s == 200 and unread == 1, f"{s} {u}")
    s, _ = req("POST", f"/api/v1/conversations/{conv_id}/read", token=buyer_tok)
    check("mark read", s == 200, f"{s}")
    s, u = req("GET", "/api/v1/conversations/unread-count", token=buyer_tok)
    unread = u.get("unread", u.get("count")) if isinstance(u, dict) else None
    check("buyer unread count is 0 after read", s == 200 and unread == 0,
          f"{s} {u}")
    s, _ = req("GET", f"/api/v1/conversations/{conv_id}/messages",
               token=transp_tok)
    check("non-participant messages 403", s == 403, f"{s}")
    s, inbox = req("GET", "/api/v1/conversations", token=farmer_tok)
    items = inbox if isinstance(inbox, list) else inbox.get("conversations", [])
    check("inbox lists conversation", s == 200 and any(
        c.get("id") == conv_id for c in items), f"{s}")

    # Manual prices
    s, p = req("POST", "/api/v1/prices/manual", token=admin_tok,
               body={"crop": "tomato", "hub": "dhaka", "price": 42,
                     "note": "smoke test observation"})
    check("admin manual price 201 real", s == 201
          and p.get("source") == "manual"
          and p.get("label") == "real", f"{s} {str(p)[:200]}")
    s, latest = req("GET", "/api/v1/prices/latest")
    rows = latest if isinstance(latest, list) else latest.get("prices", [])
    hit = [r for r in rows if r.get("crop") == "tomato"
           and r.get("hub") == "dhaka"]
    check("latest prices has real tomato/dhaka", s == 200 and hit
          and hit[0].get("label") == "real", f"{s}")
    s, p2 = req("POST", "/api/v1/prices/manual", token=admin_tok,
                body={"crop": "tomato", "hub": "dhaka", "price": 43})
    check("manual price re-entry updates (200)", s == 200, f"{s} {str(p2)[:120]}")
    s, _ = req("POST", "/api/v1/prices/manual", token=farmer_tok,
               body={"crop": "tomato", "hub": "dhaka", "price": 44})
    check("manual price farmer 403", s == 403, f"{s}")

    # Assistant diagnostics (no Gemini key in this VM: template expected)
    s, st = req("GET", "/api/v1/assistant/status", token=admin_tok)
    check("assistant status admin 200", s == 200
          and st.get("key_configured") is False, f"{s} {st}")
    s, t = req("POST", "/api/v1/assistant/test", token=admin_tok)
    check("assistant test probe (no key)", s == 200
          and t.get("ok") is False and "key" in str(t.get("error", "")).lower(),
          f"{s} {t}")
    s, _ = req("POST", "/api/v1/assistant/test", token=farmer_tok)
    check("assistant test farmer 403", s == 403, f"{s}")
    # Streaming (template mode, no key): read raw SSE.
    data = json.dumps({"message": "How do I store tomatoes?",
                       "language": "en"}).encode()
    r = urllib.request.Request(BASE + "/api/v1/assistant/chat/stream",
                               data=data, method="POST")
    r.add_header("Authorization", f"Bearer {farmer_tok}")
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            sse = resp.read().decode()
            check("assistant stream template SSE", resp.status == 200
                  and "event: done" in sse and "template" in sse,
                  f"{resp.status} {sse[:200]}")
    except urllib.error.HTTPError as e:
        check("assistant stream template SSE", False, f"HTTP {e.code}")

    print(f"\n{PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
