"""Provider-agnostic AI interfaces. Swap providers via EMBEDDING_PROVIDER / VISION_PROVIDER."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field


class AIUnavailable(Exception):
    """Provider not configured or failing; the pipeline degrades instead of faking output."""


class EmbeddingProvider(Protocol):
    model_id: str
    dim: int

    async def embed_images(self, images: list[bytes]) -> list[list[float]]:
        """L2-normalised vectors, one per input JPEG."""
        ...

    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


Category = Literal[
    "tops",
    "outerwear",
    "dresses",
    "bottoms",
    "suits",
    "knitwear",
    "activewear",
    "underwear",
    "shoes",
    "bags",
    "accessories",
    "jewelry",
    "watches",
    "eyewear",
    "headwear",
    "other",
]


class ColorInfo(BaseModel):
    name: str
    hex: str


class BrandGuess(BaseModel):
    name: str | None
    confidence: Literal["none", "low", "medium", "high"]
    evidence: str | None


class SearchQueries(BaseModel):
    en: list[str] = Field(default_factory=list)
    ru: list[str] = Field(default_factory=list)
    zh: list[str] = Field(default_factory=list)


class ImageAnalysis(BaseModel):
    is_product: bool
    rejection_reason: str | None
    category: Category
    subcategory: str
    title_en: str
    title_ru: str
    gender: Literal["women", "men", "unisex", "kids", "unknown"]
    colors: list[ColorInfo]
    material: str | None
    pattern: str | None
    silhouette: str | None
    style: list[str]
    features: list[str]
    brand: BrandGuess
    queries: SearchQueries
    discover_queries: SearchQueries


class VisionAnalyzer(Protocol):
    model_id: str

    async def analyze(self, image_jpeg: bytes, *, deep: bool) -> ImageAnalysis: ...
