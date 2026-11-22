"""Read and validate form fields, like a Nest ValidationPipe."""
from __future__ import annotations

from typing import Optional

from flask import request

from app.common.errors import AppError


def text(field: str, required: bool = False, label: Optional[str] = None,
         max_length: int = 200) -> Optional[str]:
    value = (request.form.get(field) or "").strip()
    if required and not value:
        raise AppError(f"El campo {label or field} es obligatorio.")
    if len(value) > max_length:
        raise AppError(f"El campo {label or field} admite máximo {max_length} caracteres.")
    return value or None


def raw(field: str, required: bool = False, label: Optional[str] = None) -> Optional[str]:
    """Like text() but untouched: passwords keep their spaces."""
    value = request.form.get(field) or ""
    if required and not value:
        raise AppError(f"El campo {label or field} es obligatorio.")
    return value or None


def integer(field: str, required: bool = False, label: Optional[str] = None) -> Optional[int]:
    value = text(field, required, label)
    if value is None:
        return None
    try:
        number = int(value)
        if abs(number) > 2**63 - 1:  # beyond Neo4j's 64-bit integers
            raise ValueError
        return number
    except ValueError:
        raise AppError(f"El campo {label or field} debe ser un número.") from None
