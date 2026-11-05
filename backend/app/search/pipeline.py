"""Visual search pipeline (runs in the worker).

uploaded -> analyzing -> embedding -> searching (providers in parallel, results stream
in as each provider finishes) -> ranking -> completed.

Every stage writes its real state to `search_sessions`; the Mini App polls it. A provider
that fails or times out is recorded as such and never blocks the others.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median
from typing import Any

import orjson
from sqlalchemy import select, text, update

from app.ai.base import AIUnavailable, ImageAnalysis
from app.ai.embeddings import build_embedding_provider
from app.ai.palette import palette
from app.ai.vision import build_vision_analyzer
from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.models import Product, SearchResult, SearchSession, User
from app.db.session import session_scope
from app.marketplace import lens, registry
from app.marketplace.base import (
    IntegrationKind,
    MarketplaceProvider,
    NormalizedProduct,
    ProviderError,
    ProviderState,
    ProviderUnavailable,
    SearchQuery,
)
from app.search.ranking import Candidate, calibrate, cosine, mark_duplicates, score
from app.services import fx, subscriptions
from app.services.app_settings import get_setting
from app.services.catalog import cached_embeddings, store_embeddings, upsert_products
from app.services.media import signed_media_url
from app.services.storage import get_storage
from app.services.thumbs import ensure_thumbs, read_thumbs, thumb_state

log = logging.getLogger(__name__)
AI_STATS_KEY = "sift:ai_stats"


async def _ai_stat(kind: str, ok: bool, err: str | None = None) -> None:
    r = get_redis()
    pipe = r.pipeline()
    pipe.hincrby(AI_STATS_KEY, f"{kind}:{'ok' if ok else 'fail'}", 1)
    pipe.hset(AI_STATS_KEY, f"{kind}:last_{'ok' if ok else 'error'}", f"{int(time.time())}|{err or ''}"[:300])
    await pipe.execute()


async def _set(search_id: uuid.UUID, **values: Any) -> None:
    async with session_scope() as s:
        await s.execute(update(SearchSession).where(SearchSession.id == search_id).values(**values))


async def _provider_status(search_id: uuid.UUID, code: str, payload: dict[str, Any]) -> None:
    async with session_scope() as s:
        await s.execute(
            text(
                "UPDATE search_sessions SET providers_status = providers_status || "
                "jsonb_build_object(CAST(:code AS text), CAST(:val AS jsonb)) WHERE id = :id"
            ),
            {"code": code, "val": orjson.dumps(payload).decode(), "id": search_id},
        )


def _queries(analysis: ImageAnalysis | None, mode: str) -> dict[str, list[str]]:
    if analysis is None:
        return {}
    src = analysis.discover_queries if mode == "discover" else analysis.queries
    q = {"en": list(src.en), "ru": list(src.ru), "zh": list(src.zh)}
    if not any(q.values()):
        q = {"en": list(analysis.queries.en), "ru": list(analysis.queries.ru), "zh": list(analysis.queries.zh)}
    return q


class SearchRun:
    def __init__(self, search: SearchSession, user: User, features: dict[str, Any], plan_code: str) -> None:
        self.search = search
        self.user = user
        self.features = features
        self.plan_code = plan_code
        self.settings = get_settings()
        self.embedder = build_embedding_provider()
        self.vision = build_vision_analyzer()
        self.query_vec: list[float] | None = None
        self.analysis: ImageAnalysis | None = None
        self.image: bytes = b""
        self.fx: dict[str, Decimal] = {}
        self.display_currency = (user.preferences or {}).get("currency") or ("RUB" if (user.language_code or "").startswith("ru") else "USD")

    # ----------------------------------------------------------------- stages
    async def analyze(self) -> None:
        await _set(self.search.id, stage="analyzing")
        try:
            self.analysis = await self.vision.analyze(self.image, deep=bool(self.features.get("deep_analysis")))
            await _ai_stat("vision", True)
        except AIUnavailable as e:
            log.warning("vision unavailable: %s", e)
            await _ai_stat("vision", False, str(e))
        data: dict[str, Any] = {"palette": await asyncio.to_thread(palette, self.image)}
        if self.analysis:
            data.update(self.analysis.model_dump())
            data["vision_model"] = self.vision.model_id
        else:
            data["vision_error"] = "unavailable"
        await _set(self.search.id, analysis=data)

    async def embed(self) -> None:
        if self.embedder.model_id == "none":  # EMBEDDING_PROVIDER=none is a choice, not a failure
            return
        await _set(self.search.id, stage="embedding")
        try:
            vec = (await self.embedder.embed_images([self.image]))[0]
            self.query_vec = vec
            await _ai_stat("embedding", True)
            await _set(self.search.id, query_embedding=vec, embedding_model=self.embedder.model_id)
        except AIUnavailable as e:
            log.warning("embeddings unavailable: %s", e)
            await _ai_stat("embedding", False, str(e))

    async def _allowed_providers(self) -> list[MarketplaceProvider]:
        opts = self.search.options or {}
        wanted = set(opts.get("marketplaces") or [])
        async with session_scope() as s:
            basic = set(await get_setting(s, "basic_marketplaces"))
        scope_all = self.features.get("marketplaces") == "all"
        out = []
        for p in registry.visible_providers():
            if wanted and p.code not in wanted:
                continue
            if not scope_all and p.code not in basic:
                continue
            out.append(p)
        return out

    async def run_providers(self) -> int:
        await _set(self.search.id, stage="searching")
        providers = await self._allowed_providers()
        q = _queries(self.analysis, self.search.mode)
        opts = self.search.options or {}
        await asyncio.gather(*(p.prepare() for p in providers))
        active = [p for p in providers if p.state() is ProviderState.ACTIVE]
        for p in providers:
            if p not in active:
                await _provider_status(self.search.id, p.code, {"state": "unavailable", "reason": p.state().value})
        if not active:
            return 0
        public = self.settings.public_base_url.rstrip("/")
        per_provider = max(10, int(self.features.get("max_candidates", 40)) // len(active))
        query = SearchQuery(
            texts=q,
            image_jpeg=self.image,
            query_embedding=self.query_vec,
            embedding_model=self.embedder.model_id if self.query_vec else None,
            category=self.analysis.category if self.analysis else None,
            gender=self.analysis.gender if self.analysis else None,
            price_min=Decimal(str(opts["price_min"])) if opts.get("price_min") is not None else None,
            price_max=Decimal(str(opts["price_max"])) if opts.get("price_max") is not None else None,
            condition=opts.get("condition"),
            limit=min(per_provider, self.settings.search_results_per_provider),
            image_public_url=(public + signed_media_url(self.search.image_key)) if self.search.image_key else None,
        )
        query.shared["web_codes"] = [p.code for p in active if p.info().kind is IntegrationKind.WEB_SEARCH]
        for p in active:
            await _provider_status(self.search.id, p.code, {"state": "searching"})
        tasks = [asyncio.create_task(self._one_provider(p, query)) for p in active]
        done, pending = await asyncio.wait(tasks, timeout=self.settings.search_total_timeout_seconds)
        for t in pending:
            t.cancel()
        for p, t in zip(active, tasks, strict=True):
            if t in pending:
                await _provider_status(self.search.id, p.code, {"state": "timeout"})
        return len(active)

    async def _one_provider(self, provider: MarketplaceProvider, query: SearchQuery) -> None:
        started = time.monotonic()
        code = provider.code
        try:
            if not query.texts and not provider.supports_image_search:
                await _provider_status(self.search.id, code, {"state": "skipped", "reason": "no_text_queries"})
                return
            items = await asyncio.wait_for(provider.search(query), timeout=provider.timeout_seconds or self.settings.provider_timeout_seconds)
            n = await self._ingest(code, items)
            await _provider_status(self.search.id, code, {"state": "done", "count": n, "ms": int((time.monotonic() - started) * 1000)})
        except ProviderUnavailable as e:
            await _provider_status(self.search.id, code, {"state": "unavailable", "reason": e.state.value})
        except TimeoutError:
            await _provider_status(self.search.id, code, {"state": "timeout"})
        except (ProviderError, Exception) as e:  # noqa: BLE001 - one source must not break the search
            log.error("provider %s failed: %s", code, e, exc_info=not isinstance(e, ProviderError))
            await _provider_status(self.search.id, code, {"state": "error"})

    async def _ingest(self, code: str, items: list[NormalizedProduct]) -> int:
        if not items:
            return 0
        async with session_scope() as s:
            ids = await upsert_products(s, items)
            cached = await cached_embeddings(s, list(ids.values()), self.embedder.model_id) if self.query_vec else {}
        vectors: dict[int, list[float]] = dict(cached)
        pairs = [(ids[(p.source, p.external_id)], p) for p in items]
        fresh = await ensure_thumbs(pairs)
        if self.query_vec is not None:
            need = [(pid, p.image_url) for pid, p in pairs if p.image_url and pid not in vectors]
            if need:
                missing = [pid for pid, _ in need if pid not in fresh]
                stored = {pid: k for pid, (k, _) in (await thumb_state(missing)).items() if k} if missing else {}
                imgs = {**(await read_thumbs(stored)), **fresh}
                todo = [(pid, u) for pid, u in need if pid in imgs]
                if todo:
                    try:
                        vecs = await self.embedder.embed_images([imgs[pid] for pid, _ in todo])
                        await _ai_stat("embedding", True)
                        new = [(pid, u, v) for (pid, u), v in zip(todo, vecs, strict=True)]
                        vectors.update({pid: v for pid, _, v in new})
                        async with session_scope() as s:
                            await store_embeddings(s, self.embedder.model_id, new)
                    except AIUnavailable as e:
                        await _ai_stat("embedding", False, str(e))
        rows = []
        for rank, p in enumerate(items):
            pid = ids[(p.source, p.external_id)]
            vec = vectors.get(pid)
            cos = cosine(self.query_vec, vec) if (self.query_vec is not None and vec is not None) else None
            rows.append(
                {
                    "search_id": self.search.id,
                    "product_id": pid,
                    "provider": code,
                    "cosine": cos,
                    "similarity_pct": calibrate(cos) if cos is not None else None,
                    "text_rank": rank,
                    "rank_score": 0.0,
                }
            )
        from sqlalchemy.dialects.postgresql import insert

        async with session_scope() as s:
            await s.execute(insert(SearchResult).values(rows).on_conflict_do_nothing(constraint="uq_search_results_search_product"))
            await s.execute(
                text("UPDATE search_sessions SET results_count = (SELECT count(*) FROM search_results WHERE search_id = :id) WHERE id = :id"),
                {"id": self.search.id},
            )
        return len(rows)

    async def rank(self) -> None:
        await _set(self.search.id, stage="ranking")
        self.fx = await fx.rates()
        async with session_scope() as s:
            rows = (
                await s.execute(
                    select(SearchResult, Product)
                    .join(Product, Product.id == SearchResult.product_id)
                    .where(SearchResult.search_id == self.search.id)
                )
            ).all()
            emb = await cached_embeddings(s, [p.id for _, p in rows], self.embedder.model_id) if self.query_vec else {}
            cands: list[Candidate] = []
            for r, p in rows:
                cands.append(
                    Candidate(
                        product_id=p.id,
                        provider=r.provider,
                        text_rank=r.text_rank,
                        cos=r.cosine,
                        price=fx.convert(p.price, p.currency, self.display_currency, self.fx) if self.fx else p.price,
                        image_url=p.image_url,
                        title=p.title,
                        embedding=emb.get(p.id),
                    )
                )
            ref = self.search.reference_price
            if self.search.mode == "cheaper" and ref is None:
                tops = sorted([c for c in cands if c.cos is not None and c.price is not None], key=lambda c: -(c.cos or 0))[:5]
                if tops:
                    ref = Decimal(str(median([float(c.price) for c in tops if c.price is not None])))
            mark_duplicates(cands)
            by_pid = {c.product_id: c for c in cands}
            for r, _ in rows:
                c = by_pid[r.product_id]
                r.is_duplicate = c.duplicate
                r.rank_score = score(c, self.search.mode, ref)
            await s.execute(
                update(SearchSession)
                .where(SearchSession.id == self.search.id)
                .values(
                    reference_price=ref,
                    reference_currency=self.display_currency if ref is not None else None,
                    results_count=sum(1 for c in cands if not c.duplicate),
                )
            )


async def run_search(search_id: uuid.UUID) -> None:
    async with session_scope() as s:
        search = await s.scalar(select(SearchSession).where(SearchSession.id == search_id).with_for_update())
        if search is None or search.status not in ("queued",):
            return  # already processed / cancelled -> idempotent re-delivery
        user = await s.get(User, search.user_id)
        assert user is not None
        ent = await subscriptions.entitlement(s, user)
        search.status = "running"
        search.started_at = datetime.now(UTC)
        features, plan_code = dict(ent.features), ent.plan.code
    run = SearchRun(search, user, features, plan_code)
    try:
        run.image = await get_storage().get(search.image_key)
        await asyncio.gather(run.analyze(), run.embed())
        if run.analysis is None and run.query_vec is None and not lens.lens_ready():
            # Without analysis and embeddings only a photo search (Lens) can still find something.
            await _fail(search_id, "ai_unavailable", refund=True)
            return
        if run.analysis is not None and not run.analysis.is_product:
            await _fail(search_id, "not_a_product", refund=True, detail=run.analysis.rejection_reason)
            return
        n_active = await run.run_providers()
        await run.rank()
        async with session_scope() as s:
            srch = await s.get(SearchSession, search_id, with_for_update=True)
            assert srch is not None
            statuses = srch.providers_status or {}
            ok = [v for v in statuses.values() if v.get("state") == "done"]
            if n_active == 0 or not ok:
                # Nothing could be queried: not the user's fault -> give the search back.
                await subscriptions.refund_search(s, srch)
            srch.status = "completed" if ok else "failed"
            srch.error = None if ok else ("no_sources" if n_active == 0 else "all_sources_failed")
            srch.stage = "done"
            srch.finished_at = datetime.now(UTC)
    except asyncio.CancelledError:
        await _fail(search_id, "cancelled", refund=True)
        raise
    except Exception:
        log.exception("search %s crashed", search_id)
        await _fail(search_id, "internal_error", refund=True)


async def _fail(search_id: uuid.UUID, code: str, *, refund: bool, detail: str | None = None) -> None:
    async with session_scope() as s:
        srch = await s.get(SearchSession, search_id, with_for_update=True)
        if srch is None:
            return
        srch.status = "failed"
        srch.stage = "done"
        srch.error = code if not detail else f"{code}: {detail[:300]}"
        srch.finished_at = datetime.now(UTC)
        if refund:
            await subscriptions.refund_search(s, srch)
