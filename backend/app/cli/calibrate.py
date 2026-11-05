"""Calibrate the similarity % on your own labelled image pairs.

The % shown to users is a linear map of cosine similarity between SIMILARITY_CALIBRATION_LOW (0 %)
and SIMILARITY_CALIBRATION_HIGH (100 %). Those bounds depend on the embedding model and the catalogue,
so measure them instead of guessing.

Input CSV (header required): image_a,image_b,label
  label = same     -> the same product (different photo / seller)
  label = similar  -> a close alternative a shopper would accept
  label = different-> unrelated item of the same category
image_a / image_b are https URLs or local paths.

Usage (inside the worker container):
  python -m app.cli.calibrate /data/uploads/pairs.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import statistics
import sys
from pathlib import Path

from app.ai.embeddings import build_embedding_provider
from app.core.config import get_settings
from app.search.ranking import cosine
from app.services.images import normalize
from app.services.remote_images import fetch_many

LABELS = ("same", "similar", "different")


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


async def _load(refs: list[str]) -> dict[str, bytes]:
    urls = [r for r in refs if r.startswith(("http://", "https://"))]
    out = await fetch_many(urls) if urls else {}
    for r in refs:
        if r not in out and not r.startswith(("http://", "https://")):
            out[r] = Path(r).read_bytes()  # noqa: ASYNC240 - one-off CLI
    return out


async def run(path: str) -> int:
    with open(path, newline="", encoding="utf-8") as f:  # noqa: ASYNC230 - one-off CLI
        rows = [r for r in csv.DictReader(f) if r.get("label") in LABELS]
    if len(rows) < 20:
        print("need at least 20 labelled pairs (100+ recommended)", file=sys.stderr)
        return 2
    refs = sorted({r["image_a"] for r in rows} | {r["image_b"] for r in rows})
    raw = await _load(refs)
    missing = [r for r in refs if r not in raw]
    if missing:
        print(f"skipping {len(missing)} images that could not be loaded", file=sys.stderr)
    st = get_settings()
    images: dict[str, bytes] = {}
    for r, b in raw.items():
        try:
            images[r] = normalize(b, max_bytes=st.upload_max_bytes, max_pixels=st.upload_max_pixels, max_side=st.upload_normalized_max_side).data
        except Exception as e:  # noqa: BLE001 - report and skip bad images
            print(f"skip {r}: {e}", file=sys.stderr)
    keys = list(images)
    emb = build_embedding_provider()
    vecs: dict[str, list[float]] = {}
    for i in range(0, len(keys), 32):
        chunk = keys[i : i + 32]
        for k, v in zip(chunk, await emb.embed_images([images[k] for k in chunk]), strict=True):
            vecs[k] = v

    by: dict[str, list[float]] = {lab: [] for lab in LABELS}
    for r in rows:
        if r["image_a"] in vecs and r["image_b"] in vecs:
            by[r["label"]].append(cosine(vecs[r["image_a"]], vecs[r["image_b"]]))

    print(f"model: {emb.model_id}")
    for lab in LABELS:
        v = by[lab]
        if v:
            print(f"{lab:>9}: n={len(v):4d}  p10={_pct(v, 0.1):.3f}  median={statistics.median(v):.3f}  p90={_pct(v, 0.9):.3f}")
    if not by["same"] or not by["different"]:
        print("need both 'same' and 'different' pairs to suggest bounds", file=sys.stderr)
        return 2
    low = _pct(by["different"], 0.9)  # 90 % of unrelated pairs land at 0 %
    high = statistics.median(by["same"])  # a typical exact match reads 100 %
    if high <= low:
        print("classes overlap: this embedding model cannot separate your data; do not show % to users", file=sys.stderr)
        return 1
    print("\nput into .env:")
    print(f"SIMILARITY_CALIBRATION_LOW={low:.3f}")
    print(f"SIMILARITY_CALIBRATION_HIGH={high:.3f}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv")
    sys.exit(asyncio.run(run(p.parse_args().csv)))


if __name__ == "__main__":
    main()
