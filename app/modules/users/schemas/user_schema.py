from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.common.errors import AppError
from app.common.forms import raw, text
from app.modules.auth.auth_user import ROLES
from app.modules.auth.schemas.login_schema import valid_email, valid_password


@dataclass(frozen=True)
class User:
    """(:User) node. password_hash is never read into this class."""

    user_id: int
    name: str
    email: str
    role: str
    created_at: datetime
    article_count: int = 0
    comment_count: int = 0
    foreign_comment_count: int = 0  # comments that survive if the user is deleted
    avatar: Optional[str] = None
    cover: Optional[str] = None


@dataclass(frozen=True)
class SaveUserSchema:
    name: str
    email: str
    role: str
    password: Optional[str]

    @classmethod
    def from_form(cls, password_required: bool) -> "SaveUserSchema":
        role = text("role") or "AUTHOR"
        if role not in ROLES:
            raise AppError("El rol debe ser ADMIN o AUTHOR.")
        password = raw("password", password_required, "contraseña")
        return cls(name=text("name", True, "nombre", 80),
                   email=valid_email(text("email", True, "correo")),
                   role=role, password=valid_password(password) if password else None)
