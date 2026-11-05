from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ImageAnalysis
from app.api.deps import get_session
from app.api.serializers import marketplace_out
from app.core.config import get_settings
from app.core.redis import get_redis
from app.marketplace import registry
from app.schemas.common import ConfigOut
from app.services.media import verify_media
from app.services.storage import get_storage

router = APIRouter()


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", include_in_schema=False)
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await session.execute(text("SELECT 1"))
    await get_redis().ping()
    return {"status": "ready"}


@router.get("/api/v1/config", response_model=ConfigOut)
async def config() -> ConfigOut:
    s = get_settings()
    cats = list(ImageAnalysis.model_fields["category"].annotation.__args__)  # type: ignore[union-attr]
    return ConfigOut(
        brand={
            "name": s.brand_name,
            "tagline": s.brand_tagline,
            "tagline_ru": s.brand_tagline_ru,
            "accent": s.brand_accent,
            "support_username": s.brand_support_username,
            "support_email": s.brand_support_email,
        },
        bot_username=s.bot_username,
        marketplaces=[m for m in (marketplace_out(p.code) for p in registry.visible_providers()) if m],
        upload={"max_bytes": s.upload_max_bytes, "formats": ["image/jpeg", "image/png", "image/webp"]},
        modes=["exact", "similar", "cheaper", "discover"],
        categories=cats,
    )


@router.get("/api/v1/media/{key:path}", include_in_schema=False)
async def media(key: str, exp: int = Query(...), sig: str = Query(...)) -> FileResponse:
    if not verify_media(key, exp, sig):
        raise HTTPException(status_code=403)
    try:
        path = get_storage().path(key)
    except ValueError as e:
        raise HTTPException(status_code=404) from e
    if not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3000"})
