from flask import Flask, flash, g, jsonify, redirect, render_template, request, url_for
import os

from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.routing import IntegerConverter

from app.common.errors import AppError, UnauthorizedError
from app.common.http import wants_json
from app.common.security import check_csrf, csrf_field, internal_path
from app.common.throttle import TooManyRequestsError
from app.database import config
from app.modules.articles.articles_controller import articles
from app.modules.articles.schemas.article_schema import STATUSES
from app.modules.auth.auth_controller import auth, auth_api
from app.modules.auth.jwt_guard import load_current_user
from app.modules.categories.categories_controller import categories
from app.modules.comments.comments_controller import comments
from app.modules.dashboard.dashboard_controller import dashboard
from app.modules.events.events_controller import live
from app.modules.tags.tags_controller import tags
from app.modules.users.profile_controller import profile
from app.modules.users.users_controller import users


PAGE_MESSAGES = {404: "Esta página no existe.", 405: "Esa acción no está permitida aquí."}
HTTP_MESSAGES = {404: "La ruta no existe.", 405: "Método no permitido en esta ruta.",
                 400: "Petición inválida.", 415: "El cuerpo debe ser JSON."}


MAX_ID = 2**63 - 1  # Neo4j integers are 64-bit


class Neo4jIdConverter(IntegerConverter):
    """<int:...> in routes: a number Neo4j cannot store simply does not match (404, not 500)."""

    def __init__(self, url_map, *args, **kwargs):
        kwargs.setdefault("max", MAX_ID)
        super().__init__(url_map, *args, **kwargs)


def create_app() -> Flask:
    app = Flask(__name__)
    app.url_map.converters["int"] = Neo4jIdConverter
    app.secret_key = config.jwt_secret  # signs the session that holds flash messages and the CSRF token
    # 6 MB per request: room for a 5 MB image plus the form fields.
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      MAX_CONTENT_LENGTH=6 * 1024 * 1024)

    if os.getenv("TRUST_PROXY") == "1":
        # Behind Tailscale Funnel: trust its X-Forwarded-* so the Origin check and secure cookies see https.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    for blueprint in (auth, auth_api, dashboard, articles, comments, users, tags, categories, live, profile):
        app.register_blueprint(blueprint)

    app.before_request(load_current_user)
    app.before_request(check_csrf)
    app.before_request(require_delete_confirmation)
    app.jinja_env.globals["csrf_field"] = csrf_field
    app.jinja_env.globals["field"] = submitted_value
    app.jinja_env.globals["field_list"] = submitted_list
    # Macros (avatar, delete button...) available in every template without importing.
    # Built after the globals above, because the module captures them.
    app.jinja_env.globals["ui"] = app.jinja_env.get_template("partials/ui.html").module

    register_error_handlers(app)

    @app.template_filter("date")
    def format_date(value):
        return value.strftime("%d/%m/%Y %H:%M") if value else "-"

    @app.context_processor
    def inject_globals():
        return {"db_target": config.db_target, "current_user": g.get("user"), "statuses": STATUSES}

    return app


def require_delete_confirmation():
    """Every */delete POST needs confirm=1; without it, ask on a page (the no-JavaScript path)."""
    if request.method != "POST" or not request.path.endswith("/delete") or request.form.get("confirm") == "1":
        return None
    if wants_json():
        return None
    return render_template("confirm.html", action=request.path,
                           title=request.form.get("confirm_title") or "Eliminar",
                           text=request.form.get("confirm_text") or "¿Seguro que quieres eliminar este registro?",
                           back=internal_path(request.referrer) or url_for("dashboard.index"))


def submitted_value(name: str, default=""):
    """What the user typed, when a form is shown again after an error; otherwise the default."""
    values = g.get("form_values")
    return values.get(name, default) if values is not None else default


def submitted_list(name: str, default):
    """Checkbox version of submitted_value(): ids as strings."""
    values = g.get("form_values")
    chosen = values.getlist(name) if values is not None else default
    return {str(value) for value in chosen}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(error: AppError):
        if wants_json():
            response = jsonify(message=error.message)
            if isinstance(error, TooManyRequestsError):
                response.headers["Retry-After"] = str(error.retry_after)
            return response, error.status
        if isinstance(error, UnauthorizedError):
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        if request.method == "POST":
            return redisplay_form(app, error)
        return render_template("error.html", message=error.message), error.status

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        if wants_json():
            return jsonify(message=HTTP_MESSAGES.get(error.code, error.description)), error.code
        if error.code == 413:
            return render_template("error.html", message="La imagen pesa más de 5 MB."), 413
        if error.code in PAGE_MESSAGES:
            return render_template("error.html", message=PAGE_MESSAGES[error.code]), error.code
        return error

    @app.errorhandler(Exception)
    def handle_unexpected(error: Exception):
        # Never show a traceback to the client; the server log keeps it.
        app.logger.exception("Unhandled error")
        if wants_json():
            return jsonify(message="Error interno del servidor."), 500
        return render_template("error.html", message="Ocurrió un error inesperado."), 500


def redisplay_form(app: Flask, error: AppError):
    """Show the page the form came from again, with the typed values and the real status code.

    The page is found from the Referer, but only if it is one of our own GET routes.
    """
    flash(error.message, "error")
    if request.endpoint and request.endpoint.startswith("auth."):
        page = request.endpoint.split(".", 1)[1]
        return render_template(f"auth/{page}.html", form=request.form,
                               email=request.form.get("email", "")), error.status
    path = internal_path(request.referrer)
    if path:
        try:
            endpoint, args = app.url_map.bind(request.host).match(path.split("?")[0], method="GET")
            g.form_values = request.form
            return app.view_functions[endpoint](**args), error.status
        except AppError as page_error:  # the page itself is not available to this user
            flash(page_error.message, "error")
        except HTTPException:
            pass
    return render_template("error.html", message=error.message), error.status
