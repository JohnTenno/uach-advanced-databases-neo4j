from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from app.common.pagination import Pagination
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
    pagination = Pagination.from_request(service.count(q), PAGE_SIZE)
    return render_template("users/index.html", section="users", q=q, pagination=pagination, total=pagination.total,
                           users=service.find_all(q, PAGE_SIZE, pagination.offset))


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
