from flask import Blueprint, flash, g, jsonify, redirect, render_template, url_for

from app.common.event_bus import events
from app.common.http import wants_json

from app.modules.auth.jwt_guard import jwt_required
from app.modules.comments.comments_service import CommentsService
from app.modules.comments.schemas.comment_schema import SaveCommentSchema

comments = Blueprint("comments", __name__)
service = CommentsService()


@comments.post("/articles/<int:article_id>/comments")
@jwt_required
def create(article_id: int):
    comment_id = service.create(article_id, SaveCommentSchema.from_form(g.user.name), g.user)
    count = len(service.find_by_article(article_id))
    events.publish("comment", article_id=article_id, count=count, by=g.user.id)
    if wants_json():
        html = render_template("comments/_item.html", c=service.find_one(comment_id))
        return jsonify(html=html, count=count), 201
    flash("Comentario publicado.", "ok")
    return redirect(url_for("articles.detail", article_id=article_id) + "#comentarios")


@comments.get("/comments/<int:comment_id>/edit")
@jwt_required
def edit(comment_id: int):
    return render_template("comments/edit.html", section="home",
                           comment=service.find_editable(comment_id, g.user))


@comments.post("/comments/<int:comment_id>")
@jwt_required
def update(comment_id: int):
    article_id = service.update(comment_id, SaveCommentSchema.from_form(g.user.name), g.user)
    events.publish("comment", article_id=article_id, count=len(service.find_by_article(article_id)), by=g.user.id)
    flash("Comentario actualizado.", "ok")
    return redirect(url_for("articles.detail", article_id=article_id) + "#comentarios")


@comments.post("/comments/<int:comment_id>/delete")
@jwt_required
def remove(comment_id: int):
    article_id = service.remove(comment_id, g.user)
    count = len(service.find_by_article(article_id))
    events.publish("comment", article_id=article_id, count=count, by=g.user.id)
    if wants_json():
        return jsonify(count=count)
    flash("Comentario eliminado.", "ok")
    return redirect(url_for("articles.detail", article_id=article_id) + "#comentarios")
