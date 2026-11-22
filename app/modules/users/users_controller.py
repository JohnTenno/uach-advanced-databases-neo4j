from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.modules.auth.jwt_guard import roles
from app.modules.users.schemas.user_schema import SaveUserSchema
from app.modules.users.users_service import UsersService

users = Blueprint("users", __name__, url_prefix="/users")
service = UsersService()
PAGE_SIZE = 20


@users.get("/")
@roles("ADMIN")
def index():
    q = request.args.get("q", "").strip()[:80]
    pages = max(1, -(-service.count(q) // PAGE_SIZE))
    page = min(max(request.args.get("page", 1, type=int), 1), pages)
    return render_template("users/index.html", section="users", q=q, page=page, pages=pages,
                           total=service.count(q), users=service.find_all(q, PAGE_SIZE, (page - 1) * PAGE_SIZE))


@users.get("/new")
@roles("ADMIN")
def new():
    return render_template("users/form.html", section="users", user=None)


@users.post("/")
@roles("ADMIN")
def create():
    service.create_from(SaveUserSchema.from_form(password_required=True))
    flash("Usuario creado.", "ok")
    return redirect(url_for("users.index"))


@users.get("/<int:user_id>/edit")
@roles("ADMIN")
def edit(user_id: int):
    if user_id == g.user.id:
        return redirect(url_for("profile.edit"))  # your own data is edited from your profile
    return render_template("users/form.html", section="users", user=service.find_one(user_id))


@users.post("/<int:user_id>")
@roles("ADMIN")
def update(user_id: int):
    service.set_role(user_id, request.form.get("role", ""), g.user.id)
    flash("Rol actualizado.", "ok")
    return redirect(url_for("users.index"))


@users.post("/<int:user_id>/delete")
@roles("ADMIN")
def remove(user_id: int):
    service.remove(user_id, g.user.id)
    flash("Usuario eliminado.", "ok")
    return redirect(url_for("users.index"))
