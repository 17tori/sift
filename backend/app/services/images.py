"""Untrusted image intake: format sniffing, size/pixel limits, EXIF stripping, normalisation."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import AppError

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF")


@dataclass(slots=True)
class NormalizedImage:
    data: bytes  # re-encoded JPEG, metadata stripped
    width: int
    height: int
    dhash: str
    source_format: str
    mime: str = "image/jpeg"


def _sniff(data: bytes) -> bool:
    if data.startswith(MAGIC[0]) or data.startswith(MAGIC[1]):
        return True
    return data[:4] == b"RIFF" and data[8:12] == b"WEBP"


def dhash(img: Image.Image, size: int = 8) -> str:
    """64-bit difference hash; used to deduplicate repeated uploads."""
    g = img.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    px = g.tobytes()
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def normalize(data: bytes, *, max_bytes: int, max_pixels: int, max_side: int) -> NormalizedImage:
    if not data:
        raise AppError("image_empty", "Файл пустой.")
    if len(data) > max_bytes:
        raise AppError("image_too_large", f"Файл больше {max_bytes // (1024 * 1024)} МБ.", status_code=413)
    if not _sniff(data):
        raise AppError("image_format", "Поддерживаются только JPG, PNG и WEBP.", status_code=415)
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format or ""
            probe.verify()
        if fmt not in ALLOWED_FORMATS:
            raise AppError("image_format", "Поддерживаются только JPG, PNG и WEBP.", status_code=415)
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            if w * h > max_pixels:
                raise AppError("image_too_many_pixels", "Слишком большое разрешение изображения.", status_code=413)
            if min(w, h) < 64:
                raise AppError("image_too_small", "Изображение слишком маленькое. Нужно хотя бы 64×64.")
            im.seek(0)  # animated WEBP/PNG: first frame only
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            else:
                im = im.convert("RGB")
            im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=90, optimize=True)  # no exif/icc -> metadata stripped
            return NormalizedImage(out.getvalue(), im.width, im.height, dhash(im), fmt)
    except AppError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as e:
        raise AppError("image_invalid", "Не удалось прочитать изображение.") from e
