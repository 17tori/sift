# syntax=docker/dockerfile:1.7
# All runtime dependencies ship manylinux wheels (asyncpg, pillow, orjson, uvloop...), so no apt layer is needed.
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
RUN pip install --only-binary=:all: --prefix=/install -r requirements.txt

FROM base AS runtime
RUN groupadd -g 10001 sift && useradd -u 10001 -g sift -s /usr/sbin/nologin -M sift \
    && mkdir -p /data/uploads && chown -R sift:sift /data
COPY --from=deps /install /usr/local
COPY --chown=sift:sift alembic.ini pyproject.toml ./
COPY --chown=sift:sift migrations ./migrations
COPY --chown=sift:sift app ./app
COPY --chown=sift:sift docker/healthcheck.py /usr/local/bin/healthcheck
USER sift
# PID 1 / signal forwarding: docker-compose sets `init: true` (tini bundled with Docker).
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
