"""JWT guard, the Flask version of JwtAuthGuard + @CurrentUser.

The token is read from ``Authorization: Bearer <token>`` (API) or from the
HttpOnly ``access_token`` cookie (web pages). The resolved user lives in g.user.
"""
from __future__ import annotations

from functools import wraps

from flask import g, request

from app.common.errors import ForbiddenError, UnauthorizedError
from app.modules.auth.auth_service import AuthService

COOKIE_NAME = "access_token"
auth_service = AuthService()


def load_current_user() -> None:
    """before_request hook: resolves g.user, or None when there is no valid token."""
    g.user = None
    token = bearer_token() or request.cookies.get(COOKIE_NAME)
    if token:
        try:
            g.user = auth_service.verify_token(token)
        except UnauthorizedError:
            g.user = None


def bearer_token():
    scheme, _, token = (request.headers.get("Authorization") or "").partition(" ")
    return token if scheme == "Bearer" and token else None


def jwt_required(view):
    @wraps(view)
    def guarded(*args, **kwargs):
        if g.user is None:
            raise UnauthorizedError("Inicia sesión para continuar.")
        return view(*args, **kwargs)
    return guarded


def roles(*allowed: str):
    def decorator(view):
        @wraps(view)
        @jwt_required
        def guarded(*args, **kwargs):
            if g.user.role not in allowed:
                raise ForbiddenError("No tienes permiso para esta sección.")
            return view(*args, **kwargs)
        return guarded
    return decorator
