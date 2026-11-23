"""Builds the admin blueprint for a catalog (tags or categories)."""
from flask import Blueprint, flash, redirect, render_template, url_for

from app.common.pagination import Pagination
from app.common.taxonomy_service import SaveTaxonomySchema, TaxonomyService
from app.modules.auth.jwt_guard import roles


PAGE_SIZE = 10


def taxonomy_blueprint(name: str, service: TaxonomyService, title: str) -> Blueprint:
    bp = Blueprint(name, __name__, url_prefix=f"/{name}")

    @bp.get("/")
    @roles("ADMIN")  # authors pick tags and categories from the article itself
    def index():
        pagination = Pagination.from_request(service.count(), PAGE_SIZE)
        return render_template("catalog/index.html", section=name, title=title, service=service, pagination=pagination,
                               items=service.find_all(PAGE_SIZE, pagination.offset))

    @bp.get("/new")
    @roles("ADMIN")
    def new():
        return render_template("catalog/form.html", section=name, title=title, service=service, item=None)

    @bp.post("/")
    @roles("ADMIN")
    def create():
        service.create(SaveTaxonomySchema.from_form())
        flash(f"{service.noun.capitalize()} creada.", "ok")
        return redirect(url_for(f"{name}.index"))

    @bp.get("/<int:item_id>/edit")
    @roles("ADMIN")
    def edit(item_id: int):
        return render_template("catalog/form.html", section=name, title=title,
                               service=service, item=service.find_one(item_id))

    @bp.post("/<int:item_id>")
    @roles("ADMIN")
    def update(item_id: int):
        service.update(item_id, SaveTaxonomySchema.from_form())
        flash(f"{service.noun.capitalize()} actualizada.", "ok")
        return redirect(url_for(f"{name}.index"))

    @bp.post("/<int:item_id>/delete")
    @roles("ADMIN")
    def remove(item_id: int):
        service.remove(item_id)
        flash(f"{service.noun.capitalize()} eliminada.", "ok")
        return redirect(url_for(f"{name}.index"))

    return bp
