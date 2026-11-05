from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.routes import admin, billing, favorites, me, public, searches
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.core.redis import close_redis
from app.db.session import dispose_engine
from app.services.telegram import close_bot

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging("api")
    yield
    await close_bot()
    await close_redis()
    await dispose_engine()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=f"{s.brand_name} API",
        version="1.0.0",
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        docs_url=None if s.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if s.is_production else "/api/openapi.json",
    )
    if s.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=s.cors_origins, allow_methods=["*"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"]
        )

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> ORJSONResponse:
        headers = {"Retry-After": str(exc.details["retry_after"])} if "retry_after" in exc.details else None
        return ORJSONResponse({"error": {"code": exc.code, "message": exc.message, **exc.details}}, status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> ORJSONResponse:
        return ORJSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Некорректный запрос.",
                    "fields": [".".join(map(str, e["loc"])) for e in exc.errors()],
                }
            },
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> ORJSONResponse:
        log.error("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return ORJSONResponse({"error": {"code": "internal_error", "message": "Что-то пошло не так. Мы уже разбираемся."}}, status_code=500)

    for r in (public.router, me.router, billing.router, searches.router, favorites.router, admin.router):
        app.include_router(r)
    return app


app = create_app()
