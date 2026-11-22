from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from flask import request
from werkzeug.datastructures import FileStorage

from app.common.errors import AppError
from app.common.forms import text

STATUSES = {"DRAFT": "Borrador", "PUBLISHED": "Publicado"}
# Which button was pressed decides the status; "save" keeps the current one.
INTENTS = {"publish": "PUBLISHED", "draft": "DRAFT", "save": None}


@dataclass(frozen=True)
class Article:
    """(:Article) node plus its author, reached through (:User)-[:WROTE]->."""

    article_id: int
    title: str
    body_text: str
    post_date: datetime
    status: str
    author_id: int
    author_name: str
    comment_count: int = 0
    tags: List[str] = ()
    categories: List[str] = ()
    image: Optional[str] = None
    author_avatar: Optional[str] = None
    like_count: int = 0
    liked: bool = False

    @property
    def excerpt(self) -> str:
        text = " ".join(self.body_text.split())
        return text if len(text) <= 280 else text[:277].rsplit(" ", 1)[0] + "…"


@dataclass(frozen=True)
class SaveArticleSchema:
    title: str
    body_text: str
    status: Optional[str]
    tag_ids: List[int] = ()
    category_ids: List[int] = ()
    image: Optional[FileStorage] = None  # the uploaded file, validated by ImageStorage
    remove_image: bool = False

    @classmethod
    def from_form(cls) -> "SaveArticleSchema":
        intent = text("intent") or "save"  # no button sent: create saves a draft, edit keeps the status
        if intent not in INTENTS:
            raise AppError("Acción no válida.")
        return cls(title=text("title", True, "título", 150),
                   body_text=text("body_text", True, "texto", 20000), status=INTENTS[intent],
                   tag_ids=ids("tag_ids"), category_ids=ids("category_ids"),
                   image=request.files.get("image"), remove_image=request.form.get("remove_image") == "1")


def ids(field: str) -> List[int]:
    """Checked boxes arrive as a list of numeric ids."""
    try:
        values = sorted({int(value) for value in request.form.getlist(field)})
    except ValueError:
        raise AppError("Selección no válida.") from None
    if any(value < 0 or value > 2**63 - 1 for value in values):
        raise AppError("Selección no válida.")
    return values
