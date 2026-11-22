from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.common.errors import AppError
from app.common.forms import text


@dataclass(frozen=True)
class Comment:
    """(:Comment)-[:ON]->(:Article), written by (:User)-[:POSTED]->."""

    comment_id: int
    article_id: int
    article_title: str
    user_id: Optional[int]
    name: str
    url: Optional[str]
    body_text: str
    created_at: datetime
    avatar: Optional[str] = None


@dataclass(frozen=True)
class SaveCommentSchema:
    name: str
    url: Optional[str]
    body_text: str

    @classmethod
    def from_form(cls, default_name: str) -> "SaveCommentSchema":
        url = text("url", label="URL", max_length=200)
        if url and not url.startswith(("http://", "https://")):
            raise AppError("La URL debe empezar con http:// o https://")
        return cls(name=text("name", label="nombre", max_length=80) or default_name, url=url,
                   body_text=text("body_text", True, "comentario", 2000))
