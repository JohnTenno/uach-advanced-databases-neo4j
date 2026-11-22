from __future__ import annotations

import re
from dataclasses import dataclass

from app.common.errors import AppError
from app.common.forms import raw, text

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


def valid_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_PATTERN.match(email) or len(email) > 120:
        raise AppError("El correo no tiene un formato válido (ejemplo: ana@correo.com).")
    return email


def valid_password(password: str) -> str:
    if len(password) < MIN_PASSWORD or len(password) > 200:
        raise AppError(f"La contraseña debe tener entre {MIN_PASSWORD} y 200 caracteres.")
    return password


@dataclass(frozen=True)
class LoginSchema:
    email: str
    password: str

    @classmethod
    def from_form(cls) -> "LoginSchema":
        return cls(email=text("email", True, "correo").lower(),
                   password=raw("password", True, "contraseña"))

    @classmethod
    def from_json(cls, body) -> "LoginSchema":
        if not isinstance(body, dict):
            raise AppError("El cuerpo debe ser un objeto JSON con email y password.")
        email, password = body.get("email"), body.get("password")
        if not isinstance(email, str) or not isinstance(password, str) or not email.strip() or not password:
            raise AppError("email y password son obligatorios y deben ser texto.")
        return cls(email=email.strip().lower(), password=password)


@dataclass(frozen=True)
class RegisterSchema:
    name: str
    email: str
    password: str

    @classmethod
    def from_form(cls) -> "RegisterSchema":
        password = raw("password", True, "contraseña")
        if password != (raw("password_confirm") or ""):
            raise AppError("Las contraseñas no coinciden.")
        return cls(name=text("name", True, "nombre", 80),
                   email=valid_email(text("email", True, "correo")),
                   password=valid_password(password))
