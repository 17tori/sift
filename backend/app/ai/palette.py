"""Deterministic dominant-colour extraction (complements the model's colour naming)."""

from __future__ import annotations

import io

from PIL import Image


def palette(jpeg: bytes, k: int = 5) -> list[dict[str, object]]:
    with Image.open(io.BytesIO(jpeg)) as im:
        im = im.convert("RGB")
        im.thumbnail((160, 160))
        w, h = im.size
        # centre crop: product photos usually frame the item centrally
        im = im.crop((int(w * 0.15), int(h * 0.15), int(w * 0.85), int(h * 0.85)))
        q = im.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette() or []
        counts = sorted(q.getcolors() or [], reverse=True)
        total = sum(c for c, _ in counts) or 1
        out = []
        for count, idx in counts[:k]:
            r, g, b = pal[idx * 3 : idx * 3 + 3]
            out.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "share": round(count / total, 3)})
        return out
