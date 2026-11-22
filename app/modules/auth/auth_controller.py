from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, g, jsonify, make_response, redirect, render_template, request, url_for

from app.common.errors import AppError
from app.common.security import internal_path
from app.common.throttle import throttle
from app.database import config
from app.modules.auth.jwt_guard import COOKIE_NAME, auth_service, jwt_required
from app.modules.auth.schemas.login_schema import LoginSchema, RegisterSchema

auth = Blueprint("auth", __name__, url_prefix="/auth")
auth_api = Blueprint("auth_api", __name__, url_prefix="/api/auth")


def _with_session(result: dict):
    """Store the JWT in an HttpOnly cookie so page JavaScript can never read it."""
    target = internal_path(request.args.get("next")) or url_for("dashboard.index")
    response = make_response(redirect(target))
    response.set_cookie(COOKIE_NAME, result["accessToken"], httponly=True, samesite="Lax",
                        secure=request.is_secure, max_age=config.jwt_expires_hours * 3600)
    return response


@auth.route("/login", methods=["GET", "POST"])
@throttle(limit=5, seconds=60)
def login():
    if request.method != "POST":  # GET and HEAD
        return render_template("auth/login.html")
    try:
        return _with_session(auth_service.login(LoginSchema.from_form()))
    except AppError as error:
        return render_template("auth/login.html", error=error.message,
                               email=request.form.get("email", "")), error.status


@auth.route("/register", methods=["GET", "POST"])
@throttle(limit=5, seconds=60)
def register():
    if request.method != "POST":
        return render_template("auth/register.html")
    try:
        return _with_session(auth_service.register(RegisterSchema.from_form()))
    except AppError as error:
        return render_template("auth/register.html", error=error.message, form=request.form), error.status


@auth.post("/logout")
def logout():
    if g.user:
        auth_service.logout(g.user)  # old tokens, even copied ones, stop working
    response = make_response(redirect(url_for("auth.login")))
    response.delete_cookie(COOKIE_NAME)
    return response


@auth_api.post("/login")
@throttle(limit=5, seconds=60)
def api_login():
    result = auth_service.login(LoginSchema.from_json(request.get_json(silent=True) or {}))
    return jsonify(accessToken=result["accessToken"], user=asdict(result["user"]))


@auth_api.get("/me")
@jwt_required
def api_me():
    return jsonify(asdict(g.user))
