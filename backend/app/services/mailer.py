"""Email delivery via SMTP (Python stdlib only — no new dependencies).

This module is the mailer API contract shared by the email-features batch:
``is_configured`` / ``send_email`` / ``public_base_url`` /
``send_password_reset_email`` / ``send_verification_email``. A sibling
worker (email verification) calls ``send_verification_email`` — keep the
names and signatures exactly as documented here.

Configuration comes from the reserved ``SMTP_*`` environment variables
(see backend/.env.example):

* ``SMTP_HOST`` — empty means "no mailer configured" (emails are never
  attempted; callers log a loud warning instead in production).
* ``SMTP_PORT`` — default 587.
* ``SMTP_USER`` / ``SMTP_PASSWORD`` — login credentials (for Gmail this is
  an app password, not the account password).
* ``SMTP_FROM`` — sender address; defaults to ``SMTP_USER`` when unset.
  Sent as ``FarmMarket <address>`` unless ``SMTP_FROM`` already includes
  a display name (a bare address in the From header is a Gmail spam
  signal; a named sender helps inbox placement, but never guarantees it).
* ``SMTP_USE_TLS`` — default True when unset; "false"/"0"/"no"/"off"
  disables STARTTLS (plain SMTP, e.g. a local dev relay).

``send_email`` NEVER raises into the request path: any failure is logged
and reported as ``False``. Callers queue sends via FastAPI BackgroundTasks
so a slow or failing mail server can never block (or fail) a response.
"""
from __future__ import annotations

import logging
import re
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from urllib.parse import urlsplit

from ..config import env

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_S = 10
DEFAULT_BASE_URL = "http://localhost:5173"


def _smtp_host() -> str:
    return env("SMTP_HOST")


def _smtp_port() -> int:
    try:
        return int(env("SMTP_PORT", "587"))
    except ValueError:
        return 587


def _smtp_user() -> str:
    return env("SMTP_USER")


def _smtp_password() -> str:
    return env("SMTP_PASSWORD")


def _smtp_from() -> str:
    return env("SMTP_FROM") or _smtp_user()


def _from_header() -> str:
    """Sender header: ``FarmMarket <address>``.

    A bare address in the From header is a spam signal for Gmail; a
    display name helps inbox placement (never guarantees it). When
    ``SMTP_FROM`` already carries a display name (e.g.
    ``Acme <a@b.c>``) it is kept verbatim. An empty/unparseable value
    falls back to the bare address as-is.
    """
    raw = _smtp_from()
    name, addr = parseaddr(raw)
    if not addr or name:
        return raw
    return formataddr(("FarmMarket", addr))


def _smtp_use_tls() -> bool:
    raw = env("SMTP_USE_TLS")
    if not raw:
        return True
    return raw.strip().lower() not in ("false", "0", "no", "off")


def is_configured() -> bool:
    """True only when host, user and password are all non-empty."""
    return bool(_smtp_host() and _smtp_user() and _smtp_password())


def send_email(to: str, subject: str, text_body: str,
               html_body: str | None = None) -> bool:
    """Send one email. Returns False on ANY failure — never raises.

    Connects with a ~10s timeout, uses STARTTLS when TLS is on (the
    port-587 default), logs in when credentials are set, and sends a
    multipart message (plain text + optional HTML alternative).
    """
    try:
        msg = EmailMessage()
        msg["From"] = _from_header()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text_body)
        if html_body:
            msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(_smtp_host(), _smtp_port(),
                          timeout=SMTP_TIMEOUT_S) as smtp:
            if _smtp_use_tls():
                smtp.starttls()
            user, password = _smtp_user(), _smtp_password()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False


_SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9.\-\[\]:]+$")


def _header_origin(request, header: str) -> str | None:
    """Origin from an Origin/Referer header, strictly validated, else None.

    Same validation as the QR base-URL helper in routers/twin.py
    (``_referer_origin``): http/https only, hostname chars only, no
    userinfo, ports allowed (dev). The path/query of a full-URL Referer
    are discarded — only scheme + host (+ port) are used. Malformed or
    absent values return None so the caller falls through to the next
    source. A request-like object without ``headers`` (e.g. a test stub)
    is treated as having no headers.
    """
    headers = getattr(request, "headers", None)
    if not headers:
        return None
    raw = headers.get(header, "").strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
        parts.port  # raises ValueError on a non-numeric port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    if "@" in parts.netloc or not parts.hostname:
        return None
    if len(parts.netloc) > 253 or not _SAFE_HOST_RE.match(parts.netloc):
        return None
    return f"{parts.scheme}://{parts.netloc}"


def public_base_url(request=None) -> str:
    """Public base URL for links in emails.

    Precedence: ``PUBLIC_BASE_URL`` env -> the request's ``Origin``
    header (validated) -> the request's ``Referer`` origin (validated)
    -> first entry of ``FRONTEND_ORIGINS`` env (comma-separated) -> the
    request's base URL (when a request is passed) -> the local dev
    frontend fallback (http://localhost:5173).

    Why Origin/Referer before FRONTEND_ORIGINS: the forgot-password and
    register requests come from the frontend page itself, so the Origin
    header IS the real frontend URL — :5173 locally, the devtunnel URL
    through a tunnel, the Vercel URL in production. The old order picked
    the first FRONTEND_ORIGINS entry, which was a stale Live Server port
    (:5500, nothing runs there), so every email link pointed at a dead
    host. Same idea as the QR base URL in routers/twin.py, which trusts
    the Referer for the same reason; a spoofed Origin/Referer only makes
    the link point at the attacker's own host (which they could link to
    freely anyway), and malformed values are ignored and fall through.
    """
    base = env("PUBLIC_BASE_URL")
    if base:
        return base.rstrip("/")
    if request is not None:
        origin = _header_origin(request, "origin")
        if origin:
            return origin
        referer = _header_origin(request, "referer")
        if referer:
            return referer
    origins = env("FRONTEND_ORIGINS")
    if origins:
        first = origins.split(",")[0].strip()
        if first:
            return first.rstrip("/")
    if request is not None:
        base_url = getattr(request, "base_url", None)
        if base_url:
            return str(base_url).rstrip("/")
    return DEFAULT_BASE_URL


def _reset_text(link: str) -> str:
    return (
        "হ্যালো,\n\n"
        "আপনি FarmMarket-এ আপনার পাসওয়ার্ড রিসেট করার অনুরোধ করেছেন।\n"
        "নিচের লিংকে ক্লিক করে নতুন পাসওয়ার্ড সেট করুন:\n\n"
        f"{link}\n\n"
        "এই লিংকটি ১ ঘণ্টা পর্যন্ত কার্যকর থাকবে।\n"
        "আপনি যদি এই অনুরোধ না করে থাকেন, তাহলে এই ইমেইলটি উপেক্ষা করুন।\n\n"
        "---\n\n"
        "Hello,\n\n"
        "You requested a password reset for your FarmMarket account.\n"
        "Click the link below to set a new password:\n\n"
        f"{link}\n\n"
        "This link expires in 1 hour.\n"
        "If you did not request this, please ignore this email.\n"
    )


def _reset_html(link: str) -> str:
    return (
        "<p>হ্যালো,</p>"
        "<p>আপনি FarmMarket-এ আপনার পাসওয়ার্ড রিসেট করার অনুরোধ করেছেন। "
        "নতুন পাসওয়ার্ড সেট করতে নিচের লিংকে ক্লিক করুন:</p>"
        f'<p><a href="{link}">{link}</a></p>'
        "<p>এই লিংকটি ১ ঘণ্টা পর্যন্ত কার্যকর থাকবে। "
        "আপনি যদি এই অনুরোধ না করে থাকেন, তাহলে এই ইমেইলটি উপেক্ষা করুন।</p>"
        "<hr>"
        "<p>Hello,</p>"
        "<p>You requested a password reset for your FarmMarket account. "
        "Click the link below to set a new password:</p>"
        f'<p><a href="{link}">{link}</a></p>'
        "<p>This link expires in 1 hour. "
        "If you did not request this, please ignore this email.</p>"
    )


def send_password_reset_email(to: str, token: str, request=None) -> bool:
    """Send the password-reset email (1-hour link). Returns send result."""
    link = f"{public_base_url(request)}/reset-password?token={token}"
    return send_email(
        to,
        "পাসওয়ার্ড রিসেট করুন · Reset your FarmMarket password",
        _reset_text(link),
        _reset_html(link),
    )


def _verification_text(link: str) -> str:
    return (
        "হ্যালো,\n\n"
        "FarmMarket-এ স্বাগতম! আপনার অ্যাকাউন্টটি নিশ্চিত করতে "
        "নিচের লিংকে ক্লিক করুন:\n\n"
        f"{link}\n\n"
        "এই লিংকটি ২৪ ঘণ্টা পর্যন্ত কার্যকর থাকবে।\n"
        "আপনি যদি FarmMarket-এ রেজিস্টার না করে থাকেন, "
        "তাহলে এই ইমেইলটি উপেক্ষা করুন।\n\n"
        "---\n\n"
        "Hello,\n\n"
        "Welcome to FarmMarket! Please confirm your account by clicking "
        "the link below:\n\n"
        f"{link}\n\n"
        "This link expires in 24 hours.\n"
        "If you did not register for FarmMarket, please ignore this email.\n"
    )


def _verification_html(link: str) -> str:
    return (
        "<p>হ্যালো,</p>"
        "<p>FarmMarket-এ স্বাগতম! আপনার অ্যাকাউন্টটি নিশ্চিত করতে "
        "নিচের লিংকে ক্লিক করুন:</p>"
        f'<p><a href="{link}">{link}</a></p>'
        "<p>এই লিংকটি ২৪ ঘণ্টা পর্যন্ত কার্যকর থাকবে। "
        "আপনি যদি FarmMarket-এ রেজিস্টার না করে থাকেন, "
        "তাহলে এই ইমেইলটি উপেক্ষা করুন।</p>"
        "<hr>"
        "<p>Hello,</p>"
        "<p>Welcome to FarmMarket! Please confirm your account by clicking "
        "the link below:</p>"
        f'<p><a href="{link}">{link}</a></p>'
        "<p>This link expires in 24 hours. "
        "If you did not register for FarmMarket, please ignore this email.</p>"
    )


def send_verification_email(to: str, token: str, request=None) -> bool:
    """Send the email-verification email (24-hour link). Returns send result."""
    link = f"{public_base_url(request)}/verify-email?token={token}"
    return send_email(
        to,
        "আপনার অ্যাকাউন্ট নিশ্চিত করুন · Confirm your FarmMarket account",
        _verification_text(link),
        _verification_html(link),
    )
