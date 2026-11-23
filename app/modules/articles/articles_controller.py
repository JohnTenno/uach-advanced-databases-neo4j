from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from app.common.errors import NotFoundError

from app.common.event_bus import events
from app.common.http import wants_json
from app.common.security import internal_path
from app.modules.articles.articles_service import ArticlesService
from app.modules.articles.schemas.article_schema import SaveArticleSchema
from app.modules.auth.jwt_guard import jwt_required
from app.modules.categories.categories_service import CategoriesService
from app.modules.comments.comments_service import CommentsService
from app.modules.tags.tags_service import TagsService

articles = Blueprint("articles", __name__, url_prefix="/articles")
COMMENT_BATCH = 10  # newest comments shown on the detail page; keep in sync with comments_controller.BATCH
service = ArticlesService()
comments = CommentsService()
catalogs = {"tags": TagsService(), "categories": CategoriesService()}
SAVED = {"PUBLISHED": "Artículo publicado.", "DRAFT": "Guardado como borrador.", None: "Cambios guardados."}



def announce(article_id: int, was_published: bool, is_published: bool) -> None:
    """Tell open feeds a post appeared, changed or left. Drafts never reach the stream."""
    if was_published or is_published:
        events.publish("post", article_id=article_id, by=g.user.id)


def render_form(article):
    """The same form creates and edits; checkboxes list every tag and category."""
    selected = {name: [item.id for item in svc.for_article(article.article_id, True)] if article else []
                for name, svc in catalogs.items()}
    return render_template("articles/form.html", section="home", article=article,
                           options={name: svc.find_all() for name, svc in catalogs.items()}, selected=selected)


@articles.get("/")
@jwt_required
def index():
    """Kept for old links: your articles now live on your profile."""
    return redirect(url_for("profile.show", tab=request.args.get("tab")))


@articles.get("/new")
@jwt_required
def new():
    return render_form(None)


@articles.post("/")
@jwt_required
def create():
    dto = SaveArticleSchema.from_form()
    article_id = service.create(dto, g.user)
    announce(article_id, False, dto.status == "PUBLISHED")
    flash(SAVED[dto.status], "ok")
    return redirect(url_for("articles.detail", article_id=article_id))


@articles.get("/<int:article_id>")
@jwt_required
def detail(article_id: int):
    article = service.find_one(article_id, g.user)
    # The newest comments first; older ones load in batches ("Ver comentarios anteriores").
    # ?comentarios=todos shows them all, so the link also works without JavaScript.
    total = comments.count_by_article(article_id)
    shown = comments.find_by_article(article_id, limit=None if request.args.get("comentarios") == "todos" else COMMENT_BATCH)
    return render_template("articles/detail.html", section="home", article=article,
                           comments=shown, comment_total=total, older=total - len(shown),
                           related=service.find_related(article, g.user) if article.status == "PUBLISHED" else [],
                           more=service.find_popular_by_author(article.author_id, exclude=article_id))


@articles.get("/<int:article_id>/edit")
@jwt_required
def edit(article_id: int):
    return render_form(service.find_editable(article_id, g.user))


@articles.post("/<int:article_id>")
@jwt_required
def update(article_id: int):
    dto = SaveArticleSchema.from_form()
    was = service.find_editable(article_id, g.user).status
    service.update(article_id, dto, g.user)
    announce(article_id, was == "PUBLISHED", (dto.status or was) == "PUBLISHED")
    flash(SAVED[dto.status], "ok")
    return redirect(url_for("articles.detail", article_id=article_id))


@articles.post("/<int:article_id>/publish")
@jwt_required
def change_status(article_id: int):
    """Publish a draft. There is no way back: a published article is edited or deleted."""
    was = service.find_editable(article_id, g.user).status
    service.set_status(article_id, "PUBLISHED", g.user)
    announce(article_id, was == "PUBLISHED", True)
    flash(SAVED["PUBLISHED"], "ok")
    return redirect(url_for("articles.detail", article_id=article_id))


@articles.post("/<int:article_id>/like")
@jwt_required
def like(article_id: int):
    liked = service.set_like(article_id, g.user, want=request.form.get("want", "1") == "1")
    article = service.find_one(article_id, g.user)
    if article.status == "PUBLISHED":
        events.publish("like", article_id=article_id, count=article.like_count, by=g.user.id)
    if wants_json():
        return jsonify(liked=liked, like_count=article.like_count)
    back = internal_path(request.referrer) or url_for("articles.detail", article_id=article_id)
    return redirect(f"{back.split('#')[0]}#articulo-{article_id}")


@articles.get("/<int:article_id>/image")
@jwt_required
def image(article_id: int):
    """The cover, with the same visibility as the article (a draft's cover is private)."""
    file = service.images.path(service.find_one(article_id, g.user).image)
    if file is None:
        raise NotFoundError("El artículo no tiene imagen.")
    response = send_file(file, max_age=0)
    response.headers["Cache-Control"] = "private, no-cache"
    return response


@articles.post("/<int:article_id>/delete")
@jwt_required
def remove(article_id: int):
    was = service.find_editable(article_id, g.user, deleting=True).status
    service.remove(article_id, g.user)
    announce(article_id, was == "PUBLISHED", False)
    flash("Artículo eliminado.", "ok")
    return redirect(url_for("profile.show"))
