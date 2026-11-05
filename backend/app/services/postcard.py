"""Archive-style postcard of a find (1080×1350 JPEG) for sharing in Telegram.

Obsidian background with light grain, the listing photo in a pointed-arch frame, provenance stamp,
title in Cormorant, price in Geist Mono and the SIFT sieve mark. Fonts ship in app/assets/fonts (OFL).
"""

from __future__ import annotations

import io
import math
import random
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1350
OBSIDIAN = (17, 17, 17)
IVORY = (245, 243, 238)
SILVER = (166, 166, 166)
ACCENT = (82, 107, 255)
RELIC = (142, 58, 64)
FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
SS = 2  # supersampling for the arch mask and the dots


@dataclass(slots=True)
class CardData:
    title: str
    marketplace: str
    price: str | None  # already formatted, e.g. "2 450 ₽"; None -> "Цена на сайте"
    number: int
    photo: bytes | None
    footer: str  # e.g. "t.me/sift_bot"


@cache
def _font(name: str, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight] if name != "Inter.ttf" else [14, weight])
        except (OSError, ValueError):
            pass
    return f


def arch_points(x0: float, y0: float, w: float, h: float, steps: int = 64) -> list[tuple[float, float]]:
    """Pointed arch outline (same proportions as the sieve mark): two arcs of radius 1.14·w/2 meeting at the apex."""
    a = w / 2
    r = a * 1.14
    rise = math.sqrt(r * r - (r - a) ** 2)
    ys = y0 + rise
    cx_l, cx_r = x0 + a + (r - a), x0 + a - (r - a)  # left side is drawn by the arc centred right of middle
    pts: list[tuple[float, float]] = [(x0, y0 + h), (x0, ys)]
    a0 = -math.pi  # the spring point (x0, ys), measured going up and over
    a1 = math.atan2(y0 - ys, x0 + a - cx_l)
    for i in range(1, steps + 1):
        t = a0 + (a1 - a0) * i / steps
        pts.append((cx_l + r * math.cos(t), ys + r * math.sin(t)))
    b0 = math.atan2(y0 - ys, x0 + a - cx_r)
    b1 = math.atan2(0, x0 + w - cx_r)
    for i in range(1, steps + 1):
        t = b0 + (b1 - b0) * i / steps
        pts.append((cx_r + r * math.cos(t), ys + r * math.sin(t)))
    pts.append((x0 + w, y0 + h))
    return pts


def sieve_dots(cols: int) -> tuple[float, float, list[tuple[float, float, float, int, int]]]:
    """Port of frontend Sieve geometry: (w, h, [(x, y, r, row, col)]) in pitch units of 14."""
    px, py, rf = 14.0, 14.31, 4.1
    rows = round(cols * 1.45)
    w, h = cols * px, rows * py
    a = w / 2
    r = a * 1.14
    rise = math.sqrt(r * r - (r - a) ** 2)
    ys = rise - 0.5
    out = []
    for row in range(rows):
        for col in range(cols):
            x, y = px / 2 + col * px, py / 2 + row * py
            side = min(x, w - x)
            if y < ys:
                d = min(side, r - math.hypot(x - (a + (r - a)), y - ys), r - math.hypot(x - (a - (r - a)), y - ys))
            else:
                d = side
            rr = rf * min(1.0, max(0.0, (d + 7.5) / 14.5))
            if rr >= 0.5:
                out.append((x, y, rr, row, col))
    return w, h, out


def _draw_sieve(img: Image.Image, x: int, y: int, width: int, cols: int = 9) -> None:
    w, h, dots = sieve_dots(cols)
    k = width / w
    lit = (round(round(cols * 1.45) * 0.69), cols // 2 + 1)
    layer = Image.new("RGBA", (int(w * k * SS) + 2, int(h * k * SS) + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for cx, cy, r, row, col in dots:
        color = ACCENT if (row, col) == lit else IVORY
        X, Y, R = cx * k * SS, cy * k * SS, r * k * SS
        d.ellipse((X - R, Y - R, X + R, Y + R), fill=(*color, 255))
    layer = layer.resize((layer.width // SS, layer.height // SS), Image.LANCZOS)
    img.alpha_composite(layer, (x, y))


def _grain(img: Image.Image, amount: int = 6, seed: int = 7) -> None:
    rnd = random.Random(seed)
    noise = Image.frombytes("L", (W // 2, H // 2), bytes(rnd.randrange(256) for _ in range((W // 2) * (H // 2))))
    noise = noise.resize((W, H), Image.NEAREST).filter(ImageFilter.GaussianBlur(0.6))
    tint = Image.new("RGBA", (W, H), (*IVORY, 0))
    tint.putalpha(noise.point(lambda v: v * amount // 255))
    img.alpha_composite(tint)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int, lines: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for wd in words:
        trial = f"{cur} {wd}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
            continue
        if cur:
            out.append(cur)
        cur = wd
        if len(out) == lines:
            break
    if cur and len(out) < lines:
        out.append(cur)
    if len(out) == lines and " ".join(out) != " ".join(words):
        last = out[-1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        out[-1] = last.rstrip() + "…"
    return out


def render(data: CardData) -> bytes:
    img = Image.new("RGBA", (W, H), (*OBSIDIAN, 255))
    _grain(img)
    d = ImageDraw.Draw(img)
    mono = _font("GeistMono.ttf", 22, 400)
    caps = f"АРХИВ SIFT · № {data.number:04d} · {date.today():%d.%m.%Y}"
    d.text((80, 70), caps, font=mono, fill=SILVER)
    d.line((80, 112, W - 80, 112), fill=(*IVORY, 40), width=1)

    # photo in the arch
    ax, ay, aw, ah = 190, 150, 700, 760
    if data.photo:
        try:
            with Image.open(io.BytesIO(data.photo)) as ph:
                photo = ImageOps.fit(ph.convert("RGB"), (aw, ah), Image.LANCZOS, centering=(0.5, 0.45))
        except OSError:
            photo = None
    else:
        photo = None
    mask = Image.new("L", (aw * SS, ah * SS), 0)
    ImageDraw.Draw(mask).polygon([(x * SS, y * SS) for x, y in arch_points(0, 0, aw, ah)], fill=255)
    mask = mask.resize((aw, ah), Image.LANCZOS)
    if photo is not None:
        img.paste(photo, (ax, ay), mask)
    else:
        img.paste(Image.new("RGB", (aw, ah), (36, 36, 36)), (ax, ay), mask)
    outline = Image.new("RGBA", (aw * SS, ah * SS), (0, 0, 0, 0))
    ImageDraw.Draw(outline).line([(x * SS, y * SS) for x, y in arch_points(0, 0, aw, ah)], fill=(*IVORY, 90), width=2 * SS)
    img.alpha_composite(outline.resize((aw, ah), Image.LANCZOS), (ax, ay))

    # provenance stamp
    stamp_font = _font("GeistMono.ttf", 22, 500)
    label = data.marketplace.upper()
    tw = d.textlength(label, font=stamp_font)
    sx, sy = 80, ay + ah + 42
    d.rectangle((sx, sy, sx + tw + 28, sy + 40), outline=RELIC, width=2)
    d.text((sx + 14, sy + 8), label, font=stamp_font, fill=(214, 150, 155))

    # title
    serif = _font("CormorantGaramond.ttf", 58, 400)
    for i, line in enumerate(_wrap(d, data.title, serif, W - 160, 2)):
        d.text((80, sy + 62 + i * 64), line, font=serif, fill=IVORY)

    # price
    price_y = H - 150
    if data.price:
        d.text((80, price_y), data.price, font=_font("GeistMono.ttf", 54, 600), fill=IVORY)
    else:
        d.text((80, price_y + 4), "Цена на сайте", font=_font("CormorantGaramond.ttf", 50, 400), fill=SILVER)

    # mark + footer
    _draw_sieve(img, W - 80 - 54, H - 160, 54)
    foot = _font("GeistMono.ttf", 20, 400)
    ft = f"SIFT · {data.footer}"
    d.text((W - 80 - 54 - 24 - d.textlength(ft, font=foot), H - 86), ft, font=foot, fill=SILVER)

    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()
