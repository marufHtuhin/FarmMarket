"""Tiny in-process per-key rate limiter (fixed 1-minute window).

Same deque pattern as the assistant limiter in gemini_assistant.py. Used
for the public auth endpoints (login / register) to slow credential
stuffing and mass account creation. Single-node only: each process keeps
its own counters, which is fine for this deployment (one uvicorn worker
behind Caddy). For multi-worker deployments, replace with a shared store
(e.g. Redis) — the allow()/reset() interface is the seam.

Limits are instance attributes so tests can monkeypatch them low without
re-importing. reset_auth_limiters() is called from the test fixtures so
the module-level limiters never leak state between tests.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    """Per-key limiter: at most `limit` allowed calls per `window_s` seconds."""

    def __init__(self, limit: int, window_s: int = 60):
        self.limit = limit
        self.window_s = window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[str(key)]
        while q and now - q[0] > self.window_s:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

    def reset(self) -> None:
        self.hits.clear()


# Login is the brute-force target: 10 attempts/min/IP is generous for a
# human (a few mistyped passwords) but useless for stuffing. Registration
# is capped higher so a classroom/demo signup burst still works.
login_limiter = RateLimiter(limit=10)
register_limiter = RateLimiter(limit=30)
# Chat sends: 30/min/user is generous for a real conversation but caps spam.
message_limiter = RateLimiter(limit=30)
# Password-reset requests: 5/min/IP — enough for a real user who mistypes
# their email, too slow to flood the reset-token table or harvest tokens.
forgot_limiter = RateLimiter(limit=5)
# Verification-email resends: 5/min per user (the endpoint is authed, so
# the key is the user id, not the IP — a shared classroom/devtunnel IP
# must not let one user exhaust another's resends).
resend_limiter = RateLimiter(limit=5)


def reset_auth_limiters() -> None:
    login_limiter.reset()
    register_limiter.reset()
    forgot_limiter.reset()
    resend_limiter.reset()


def reset_message_limiter() -> None:
    message_limiter.reset()
