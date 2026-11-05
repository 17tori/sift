"""Similarity calibration, ranking and de-duplication."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal

from app.core.config import get_settings


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def calibrate(cos: float, low: float | None = None, high: float | None = None) -> int:
    s = get_settings()
    lo = s.similarity_calibration_low if low is None else low
    hi = s.similarity_calibration_high if high is None else high
    if cos <= lo:
        return 0
    if cos >= hi:
        return 100
    return round((cos - lo) / (hi - lo) * 100)


@dataclass(slots=True)
class Candidate:
    product_id: int
    provider: str
    text_rank: int
    cos: float | None
    price: Decimal | None  # converted to a common currency when possible
    image_url: str | None
    title: str
    embedding: list[float] | None = None
    duplicate: bool = False
    score: float = 0.0


def score(c: Candidate, mode: str, reference_price: Decimal | None) -> float:
    text_component = 1.0 / (1.0 + c.text_rank)
    if c.cos is None:
        base = 0.25 * text_component  # never outranks a real visual match
    else:
        weight = {"exact": 1.0, "similar": 0.92, "cheaper": 0.85, "discover": 0.75}.get(mode, 0.9)
        base = c.cos * weight + 0.08 * text_component
    if mode == "cheaper" and reference_price and c.price is not None and reference_price > 0:
        ratio = float(c.price / reference_price)
        base += 0.15 * max(0.0, 1.0 - ratio)  # cheaper -> bonus
        if ratio >= 1.0:
            base -= 0.3  # not cheaper -> pushed down
    return round(base, 6)


_norm = re.compile(r"[^a-zа-я0-9一-鿿]+")


def _title_key(t: str) -> str:
    return _norm.sub(" ", t.lower()).strip()[:80]


def mark_duplicates(cands: list[Candidate], threshold: float | None = None) -> None:
    """Same listing seen twice (same image, or near-identical embedding+title within one source)."""
    thr = threshold if threshold is not None else get_settings().duplicate_cosine_threshold
    ordered = sorted(cands, key=lambda c: (-(c.cos or -1), c.price or Decimal("1e12")))
    kept: list[Candidate] = []
    seen_images: set[str] = set()
    for c in ordered:
        if c.image_url and c.image_url in seen_images:
            c.duplicate = True
            continue
        dup = False
        if c.embedding is not None:
            for k in kept:
                if k.provider == c.provider and k.embedding is not None and _title_key(k.title) == _title_key(c.title):
                    if cosine(k.embedding, c.embedding) >= thr:
                        dup = True
                        break
        if dup:
            c.duplicate = True
            continue
        if c.image_url:
            seen_images.add(c.image_url)
        kept.append(c)
