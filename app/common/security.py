"""CSRF protection and safe redirects for the HTML side of the app.

CSRF: a random token lives in the signed Flask session and every POST form
sends it back in a hidden field (synchronizer token pattern). The JSON API is
exempt because it authenticates with a Bearer header, which a browser never
attaches on its own. A foreign Origin header is rejected as a second check.
"""
from __future__ import annotations

import hmac
import secrets
from typing import Optional
from urllib.parse import urlsplit

from flask import request, session
from markupsafe import Markup

from app.common.errors import AppError

SESSION_KEY = "csrf_token"


class CsrfError(AppError):
    status = 400


def csrf_token() -> str:
    if SESSION_KEY not in session:
        session[SESSION_KEY] = secrets.token_urlsafe(32)
    return session[SESSION_KEY]


def csrf_field() -> Markup:
    return Markup(f'<input type="hidden" name="csrf_token" value="{csrf_token()}">')


def check_csrf() -> None:
    """before_request hook for every non-API POST."""
    if request.method != "POST" or request.path.startswith("/api/"):
        return
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        raise CsrfError("La petición viene de otro sitio y se rechazó.")
    sent = request.form.get("csrf_token", "")
    if not sent or not hmac.compare_digest(sent, session.get(SESSION_KEY, "")):
        raise CsrfError("La página expiró. Vuelve a intentarlo.")


def internal_path(target: Optional[str]) -> Optional[str]:
    """Return target only when it is a path inside this app, else None.

    Accepts '/articles/3?x=1' or a full URL on our own host (Referer);
    rejects other hosts, '//host' and anything with a backslash.
    """
    if not target or "\\" in target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        if parts.netloc != request.host or parts.scheme not in ("http", "https"):
            return None
    path = parts.path or "/"
    if not path.startswith("/") or path.startswith("//"):
        return None
    return path + (f"?{parts.query}" if parts.query else "")
