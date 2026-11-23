from flask import Blueprint, flash, g, make_response, redirect, render_template, request, send_file, url_for

from app.common.errors import NotFoundError
from app.common.pagination import Pagination
from app.common.forms import raw, text
from app.database import config
from app.modules.auth.jwt_guard import COOKIE_NAME, auth_service
from app.modules.auth.schemas.login_schema import valid_email, valid_password
from app.common.image_storage import ImageStorage
from app.modules.articles.articles_service import ArticlesService
from app.modules.auth.jwt_guard import jwt_required
from app.modules.users.users_service import UsersService

profile = Blueprint("profile", __name__, url_prefix="/profile")
users, articles, images = UsersService(), ArticlesService(), ImageStorage()
PAGE_SIZE = 10
PHOTO_PAGE_SIZE = 12
TABS = {"posts": "PUBLISHED", "photos": "PUBLISHED", "drafts": "DRAFT"}


@profile.get("/")
@profile.get("/<int:user_id>")
@jwt_required
def show(user_id: int = None):
    """A user's page: who they are, their numbers and their articles. Drafts tab only on your own."""
    user = users.find_one(user_id or g.user.id)
    mine = user.user_id == g.user.id
    tab = request.args.get("tab") if request.args.get("tab") in TABS else "posts"
    if tab == "drafts" and not mine:
        tab = "posts"
    published = articles.count_by_author(user.user_id)
    drafts = articles.count_by_author(user.user_id, "DRAFT") if mine else 0
    photos = tab == "photos"
    size = PHOTO_PAGE_SIZE if photos else PAGE_SIZE
    total = drafts if tab == "drafts" else articles.count_by_author(user.user_id, with_image=True) if photos else published
    pagination = Pagination.from_request(total, size)
    items = articles.find_by_author(user.user_id, g.user, TABS[tab], limit=size,
                                    offset=pagination.offset, with_image=photos)
    return render_template("users/profile.html", section="profile" if mine else "", profile_user=user, mine=mine,
                           tab=tab, articles=items, published=published, drafts=drafts,
                           stats=users.profile_stats(user.user_id), pagination=pagination,
                           popular=articles.find_popular_by_author(user.user_id),
                           community=users.community(user.user_id), topics=users.topics(user.user_id))


@profile.get("/edit")
@jwt_required
def edit():
    return render_template("users/profile_edit.html", section="profile", user=users.find_one(g.user.id))


@profile.post("/edit")
@jwt_required
def update():
    """Account data plus photos. Each photo is optional: a new file replaces the old one,
    the checkbox removes it. Everything is validated before any file is written."""
    name = text("name", True, "nombre", 80)
    email = valid_email(text("email", True, "correo"))
    new_password = raw("new_password", False, "contraseña nueva")
    if new_password:
        valid_password(new_password)
    # Photos first: an invalid file must fail before the account data is touched.
    avatar = images.save(request.files.get("avatar"))
    try:
        cover = images.save(request.files.get("cover"))
    except Exception:
        images.delete(avatar)
        raise
    try:
        version = users.update_account(g.user.id, name, email, new_password or None,
                                       raw("current_password", False, "contraseña actual"))
        replaced = users.set_photos(g.user.id, avatar, cover, request.form.get("remove_avatar") == "1",
                                    request.form.get("remove_cover") == "1")
    except Exception:
        images.delete(avatar)
        images.delete(cover)
        raise
    images.delete(replaced["avatar"])
    images.delete(replaced["cover"])
    flash("Perfil actualizado.", "ok")
    response = make_response(redirect(url_for("profile.show")))
    if version != g.user.token_version:
        # A new password revokes every old token, this one too, so hand out a fresh one.
        fresh = users.find_by_email_with_hash(email)
        token = auth_service.sign(auth_service._to_auth_user(fresh))
        response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="Lax", secure=request.is_secure,
                            max_age=config.jwt_expires_hours * 3600)
    return response


@profile.get("/<int:user_id>/<any(avatar, cover):kind>")
@jwt_required
def photo(user_id: int, kind: str):
    """The URL carries ?v=<file>, so a new photo gets a new URL and the old one can be cached."""
    file = images.path(getattr(users.find_one(user_id), kind))
    if file is None:
        raise NotFoundError("El usuario no tiene esa foto.")
    response = send_file(file, max_age=86400)
    response.headers["Cache-Control"] = "private, max-age=86400"
    return response
