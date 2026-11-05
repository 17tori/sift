from __future__ import annotations

import io
import time

import orjson
from PIL import Image

from app.core.security import sign_init_data


def init_data(user_id: int, username: str = "tester", start_param: str | None = None, auth_date: int | None = None) -> str:
    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": orjson.dumps({"id": user_id, "first_name": "Test", "username": username, "language_code": "ru"}).decode(),
    }
    if start_param:
        fields["start_param"] = start_param
    return sign_init_data(fields, "123456:TEST-TOKEN")


def image_bytes(fmt: str = "JPEG", size: tuple[int, int] = (400, 300), color: tuple[int, int, int] = (20, 30, 200)) -> bytes:
    im = Image.new("RGB", size, color)
    for x in range(0, size[0], 20):
        for y in range(size[1] // 3, size[1] // 2):
            im.putpixel((x, y), (250, 250, 250))
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()
