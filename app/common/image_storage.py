"""Article cover images, stored on disk inside the project but outside static/.

Kept local on purpose: the app works right after cloning, with no external
account or secret keys. Files are served through a route that applies the
article's visibility rules, so a draft's cover is private too.
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path
from typing import Optional

from PIL import Image, ImageSequence, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from app.common.errors import AppError

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
MAX_BYTES = 5 * 1024 * 1024
MAX_SIDE = 8000
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}
MAX_FRAMES = 500  # animated GIF/WebP: every frame is decoded, so cap how many


class ImageStorage:
    def save(self, upload: Optional[FileStorage]) -> Optional[str]:
        """Validate and store an uploaded image; returns its file name, or None if nothing was sent."""
        if upload is None or not upload.filename:
            return None
        data = upload.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise AppError("La imagen pesa más de 5 MB.")
        extension = self._validate(data)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{extension}"
        (UPLOAD_DIR / name).write_bytes(data)
        return name

    def path(self, name: Optional[str]) -> Optional[Path]:
        """Absolute path of a stored image, only for names this class generated."""
        if not name or "/" in name or "\\" in name or name.startswith("."):
            return None
        file = UPLOAD_DIR / name
        return file if file.is_file() else None

    def delete(self, name: Optional[str]) -> None:
        file = self.path(name)
        if file:
            file.unlink(missing_ok=True)

    @staticmethod
    def _validate(data: bytes) -> str:
        """The whole file must decode as JPG, PNG, WebP or GIF; the extension the browser sent is ignored."""
        invalid = AppError("La imagen debe ser JPG, PNG, WebP o GIF y no estar dañada.")
        try:
            with Image.open(io.BytesIO(data)) as image:
                kind = FORMATS.get(image.format)
                if kind is None:
                    raise invalid
                width, height = image.size
                if getattr(image, "n_frames", 1) > MAX_FRAMES:
                    raise AppError(f"La animación tiene más de {MAX_FRAMES} cuadros.")
                for frame in ImageSequence.Iterator(image):
                    frame.load()  # decodes every pixel of every frame, so a corrupt file fails here
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise invalid from None
        if width > MAX_SIDE or height > MAX_SIDE:
            raise AppError(f"La imagen mide más de {MAX_SIDE} px por lado.")
        return kind
