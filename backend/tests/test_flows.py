"""Integration tests against real Postgres (pgvector) + Redis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.ai.base import BrandGuess, ColorInfo, ImageAnalysis, SearchQueries
from app.core.errors import AppError, QuotaExceeded
from app.db.models import Payment, SearchResult, SearchSession, Subscription, User
from app.db.session import session_scope
from app.marketplace.base import IntegrationKind, MarketplaceProvider, NormalizedProduct, ProviderError, SearchQuery
from app.services import payments, subscriptions, trial
from app.services.users import TelegramIdentity, get_or_create_user
from tests.helpers import image_bytes, init_data

pytestmark = pytest.mark.usefixtures("db")


def ident(tg: int, name: str = "u") -> TelegramIdentity:
    return TelegramIdentity(tg, name, name.title(), None, "ru")


class FakeBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def create_invoice_link(self, **kw: Any) -> str:
        self.calls.append(("create_invoice_link", kw))
        return f"https://t.me/$invoice_{kw['payload']}"

    async def refund_star_payment(self, **kw: Any) -> bool:
        self.calls.append(("refund_star_payment", kw))
        return True

    async def edit_user_star_subscription(self, **kw: Any) -> bool:
        self.calls.append(("edit_user_star_subscription", kw))
        return True


@pytest.fixture
def bot(monkeypatch: pytest.MonkeyPatch) -> FakeBot:
    fb = FakeBot()
    monkeypatch.setattr(payments, "get_bot", lambda: fb)
    return fb


async def test_registration_idempotent_and_referrals() -> None:
    async with session_scope() as s:
        a, created = await get_or_create_user(s, ident(1, "alice"))
        assert created
        code = a.referral_code
    async with session_scope() as s:
        a2, created = await get_or_create_user(s, ident(1, "alice"), start_param=f"ref_{code}")
        assert not created and a2.id == a.id and a2.referred_by_id is None  # existing users are never attributed
        b, created = await get_or_create_user(s, ident(2, "bob"), start_param=f"ref_{code}")
        assert created and b.referred_by_id == a.id
    async with session_scope() as s:
        alice = await s.get(User, a.id)
        bob = await s.get(User, b.id)
        assert alice.bonus_searches == 3 and bob.bonus_searches == 2
        # first purchase reward is granted exactly once
        from app.services import referrals

        await referrals.on_first_purchase(s, bob.id)
        await referrals.on_first_purchase(s, bob.id)
    async with session_scope() as s:
        assert (await s.get(User, a.id)).bonus_searches == 23


async def test_self_referral_impossible() -> None:
    async with session_scope() as s:
        u, _ = await get_or_create_user(s, ident(10), start_param="ref_NOSUCHCD")
        assert u.referred_by_id is None


async def test_trial_once() -> None:
    async with session_scope() as s:
        u, _ = await get_or_create_user(s, ident(3))
        sub = await trial.activate(s, u)
        assert sub.plan_code == "pro" and sub.source == "trial"
    async with session_scope() as s:
        u = await s.get(User, u.id)
        ent = await subscriptions.entitlement(s, u)
        assert ent.plan.code == "pro" and ent.is_trial
        with pytest.raises(AppError):
            await trial.activate(s, u)


async def test_quota_and_bonus() -> None:
    async with session_scope() as s:
        u, _ = await get_or_create_user(s, ident(4))
        uid = u.id
    for _ in range(3):  # free: 3/day
        async with session_scope() as s:
            u = await s.get(User, uid)
            _, bonus = await subscriptions.reserve_search(s, u)
            assert not bonus
            s.add(SearchSession(user_id=uid, image_key="k", image_hash="h", image_width=1, image_height=1))
    async with session_scope() as s:
        u = await s.get(User, uid)
        with pytest.raises(QuotaExceeded):
            await subscriptions.reserve_search(s, u)
        u.bonus_searches = 1
    async with session_scope() as s:
        u = await s.get(User, uid)
        _, bonus = await subscriptions.reserve_search(s, u)
        assert bonus and (await s.get(User, uid)).bonus_searches == 0


async def _intent(bot: FakeBot, tg: int, plan: str = "pro") -> tuple[User, Any]:
    async with session_scope() as s:
        u, _ = await get_or_create_user(s, ident(tg))
        intent = await payments.create_invoice(s, u, plan)
    return u, intent


async def test_payment_lifecycle(bot: FakeBot) -> None:
    u, intent = await _intent(bot, 5)
    call = bot.calls[0][1]
    assert call["currency"] == "XTR" and call["prices"][0].amount == 299 and call["subscription_period"] == 2592000

    async with session_scope() as s:
        assert not (await payments.validate_pre_checkout(s, 777, intent.payload, "XTR", 299)).ok  # other user
        assert not (await payments.validate_pre_checkout(s, 5, intent.payload, "XTR", 1)).ok  # wrong amount
        assert not (await payments.validate_pre_checkout(s, 5, "sub:deadbeef", "XTR", 299)).ok
        assert (await payments.validate_pre_checkout(s, 5, intent.payload, "XTR", 299)).ok
        # nothing granted before successful_payment
        assert (await subscriptions.entitlement(s, await s.get(User, u.id))).plan.code == "free"

    exp1 = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    kw = dict(telegram_user_id=5, payload=intent.payload, currency="XTR", total_amount=299, provider_payment_charge_id=None, raw={})
    async with session_scope() as s:
        out = await payments.process_successful_payment(
            s, **kw, telegram_payment_charge_id="ch_1", is_recurring=True, is_first_recurring=True, subscription_expiration_date=exp1
        )
        assert not out.duplicate and out.subscription.plan_code == "pro" and out.subscription.auto_renew
    async with session_scope() as s:  # replayed update -> ignored
        out = await payments.process_successful_payment(
            s, **kw, telegram_payment_charge_id="ch_1", is_recurring=True, is_first_recurring=True, subscription_expiration_date=exp1
        )
        assert out.duplicate
        assert not (await payments.validate_pre_checkout(s, 5, intent.payload, "XTR", 299)).ok  # already paid

    exp2 = exp1 + 30 * 86400
    async with session_scope() as s:  # renewal
        out = await payments.process_successful_payment(
            s, **kw, telegram_payment_charge_id="ch_2", is_recurring=True, is_first_recurring=False, subscription_expiration_date=exp2
        )
        assert out.renewal and int(out.subscription.expires_at.timestamp()) == exp2
    async with session_scope() as s:
        assert await s.scalar(select(func.count()).select_from(Subscription).where(Subscription.user_id == u.id)) == 1
        assert await s.scalar(select(func.count()).select_from(Payment)) == 2
        sub = await subscriptions.active_subscription(s, u.id)
        user = await s.get(User, u.id)
        await payments.set_auto_renew(s, user, sub.id, False)
    assert bot.calls[-1] == ("edit_user_star_subscription", {"user_id": 5, "telegram_payment_charge_id": "ch_1", "is_canceled": True})
    async with session_scope() as s:
        pay = await s.scalar(select(Payment).where(Payment.telegram_payment_charge_id == "ch_2"))
        refunded = await payments.refund(s, pay.id)
        assert refunded.status == "refunded"
    async with session_scope() as s:
        assert (await subscriptions.entitlement(s, await s.get(User, u.id))).plan.code == "free"


async def test_invoice_reused(bot: FakeBot) -> None:
    _, a = await _intent(bot, 6)
    _, b = await _intent(bot, 6)
    assert a.id == b.id and len(bot.calls) == 1


async def test_free_plan_not_purchasable(bot: FakeBot) -> None:
    with pytest.raises(AppError):
        await _intent(bot, 7, "free")


# --------------------------------------------------------------------- API + pipeline
class FakeEmbedder:
    model_id = "test:emb"
    dim = 1024

    async def embed_images(self, images: list[bytes]) -> list[list[float]]:
        # deterministic: brighter thumbnails are "closer" to the query
        pad = [0.0] * 1020
        return [([1.0, 0.0, 0.0, 0.0] if i == 0 else [0.8, 0.6, 0.0, 0.0]) + pad for i, _ in enumerate(images)]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class FakeVision:
    model_id = "test:vision"

    async def analyze(self, image_jpeg: bytes, *, deep: bool) -> ImageAnalysis:
        q = SearchQueries(en=["blue knit sweater"], ru=["синий свитер"], zh=["蓝色毛衣"])
        return ImageAnalysis(
            is_product=True,
            rejection_reason=None,
            category="knitwear",
            subcategory="sweater",
            title_en="Blue knit sweater",
            title_ru="Синий вязаный свитер",
            gender="unisex",
            colors=[ColorInfo(name="blue", hex="#1e3cc8")],
            material="wool",
            pattern=None,
            silhouette="oversized",
            style=["casual"],
            features=["ribbed cuffs"],
            brand=BrandGuess(name=None, confidence="none", evidence=None),
            queries=q,
            discover_queries=q,
        )


class FakeShop(MarketplaceProvider):
    code = "ebay"
    name = "eBay"
    url = "https://ebay.test"
    kind = IntegrationKind.OFFICIAL_API

    def configured(self) -> bool:
        return True

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        assert query.texts["en"] == ["blue knit sweater"]
        return [
            NormalizedProduct("ebay", f"id{i}", f"Sweater {i}", f"https://ebay.test/{i}", f"https://img.test/{i}.jpg", Decimal(10 + i), "USD")
            for i in range(3)
        ]

    async def get_product(self, external_id: str) -> NormalizedProduct | None:
        return None

    def normalize_product(self, raw: dict[str, Any]) -> NormalizedProduct | None:
        return None


class BrokenShop(FakeShop):
    code = "aliexpress"

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        raise ProviderError("boom")


@pytest.fixture
def pipeline_fakes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    import app.search.pipeline as pl
    from app.services import search_service

    monkeypatch.setattr(pl, "build_embedding_provider", lambda: FakeEmbedder())
    monkeypatch.setattr(pl, "build_vision_analyzer", lambda: FakeVision())
    monkeypatch.setattr(pl.registry, "visible_providers", lambda: [FakeShop(True), BrokenShop(True)])

    async def fake_fetch(urls: list[str], concurrency: int = 12) -> dict[str, bytes]:
        return {u: b"jpeg" for u in urls}

    from app.services import thumbs

    monkeypatch.setattr(thumbs, "fetch_many", fake_fetch)
    queued: list[str] = []
    monkeypatch.setattr(search_service, "enqueue", lambda s: queued.append(str(s.id)))
    return queued


async def test_api_end_to_end(pipeline_fakes: list[str]) -> None:
    from app.api.main import create_app
    from app.search.pipeline import run_search

    app = create_app()
    h = {"Authorization": "tma " + init_data(100, "eve")}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/v1/me")).status_code == 401
        me = (await c.get("/api/v1/me", headers=h)).json()
        assert me["plan"]["code"] == "free" and me["quota"]["remaining"] == 3 and me["trial"]["available"]
        cfg = (await c.get("/api/v1/config")).json()
        assert "goofish" not in [m["code"] for m in cfg["marketplaces"]]
        bad = await c.post("/api/v1/searches", headers=h, files={"image": ("x.gif", b"GIF89a", "image/gif")})
        assert bad.status_code == 415
        locked = await c.post("/api/v1/searches", headers=h, data={"mode": "discover"}, files={"image": ("a.jpg", image_bytes(), "image/jpeg")})
        assert locked.status_code == 403
        r = await c.post("/api/v1/searches", headers={**h, "Idempotency-Key": "k1"}, files={"image": ("a.jpg", image_bytes(), "image/jpeg")})
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        r2 = await c.post("/api/v1/searches", headers={**h, "Idempotency-Key": "k1"}, files={"image": ("a.jpg", image_bytes(), "image/jpeg")})
        assert r2.json()["id"] == sid and pipeline_fakes == [sid]

        import uuid

        await run_search(uuid.UUID(sid))
        s = (await c.get(f"/api/v1/searches/{sid}", headers=h)).json()
        assert s["status"] == "completed" and s["providers"]["ebay"]["state"] == "done"
        assert s["providers"]["aliexpress"]["state"] == "error" and s["has_similarity"]
        res = (await c.get(f"/api/v1/searches/{sid}/results", headers=h)).json()
        assert res["total"] == 3 and all(i["similarity"] is not None for i in res["items"])
        # another user cannot read it
        other = {"Authorization": "tma " + init_data(101, "mallory")}
        assert (await c.get(f"/api/v1/searches/{sid}/results", headers=other)).status_code == 404
        pid = res["items"][0]["product_id"]
        assert (await c.post("/api/v1/favorites", headers=other, json={"product_id": pid})).status_code == 403
        assert (await c.post("/api/v1/favorites", headers=h, json={"product_id": pid, "search_id": sid})).status_code == 201
        favs = (await c.get("/api/v1/favorites", headers=h)).json()
        assert len(favs) == 1 and favs[0]["product"]["product_id"] == pid
        alert = await c.patch(f"/api/v1/favorites/{favs[0]['id']}", headers=h, json={"price_alert": True})
        assert alert.status_code == 403  # ULTRA only
        hist = (await c.get("/api/v1/history", headers=h)).json()
        assert hist["items"][0]["id"] == sid and hist["items"][0]["title"] == "Синий вязаный свитер"
        img = await c.get(hist["items"][0]["image_url"])
        assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
        assert (await c.get(hist["items"][0]["image_url"].replace("sig=", "sig=0"))).status_code == 403
        # admin
        assert (await c.get("/api/v1/admin/overview", headers=h)).status_code == 403
        adm = {"Authorization": "tma " + init_data(999, "admin")}
        ov = (await c.get("/api/v1/admin/overview", headers=adm)).json()
        assert ov["users_total"] >= 2 and ov["searches_24h"] == 1
        st = (await c.get("/api/v1/admin/stats?days=7", headers=adm)).json()
        assert len(st) == 7 and st[-1]["searches"] == 1
        p = await c.patch("/api/v1/admin/plans/pro", headers=adm, json={"price_stars": 349})
        assert p.json()["price_stars"] == 349
        assert (await c.get("/api/v1/plans")).json()[1]["price_stars"] == 349

    async with session_scope() as s:
        assert await s.scalar(select(func.count()).select_from(SearchResult)) == 3


async def test_failed_search_refunds_quota(pipeline_fakes: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    import uuid

    import app.search.pipeline as pl
    from app.ai.base import AIUnavailable
    from app.api.main import create_app

    class DeadVision(FakeVision):
        async def analyze(self, image_jpeg: bytes, *, deep: bool) -> ImageAnalysis:
            raise AIUnavailable("down")

    class DeadEmb(FakeEmbedder):
        async def embed_images(self, images: list[bytes]) -> list[list[float]]:
            raise AIUnavailable("down")

    monkeypatch.setattr(pl, "build_embedding_provider", lambda: DeadEmb())
    monkeypatch.setattr(pl, "build_vision_analyzer", lambda: DeadVision())
    h = {"Authorization": "tma " + init_data(200)}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t") as c:
        sid = (await c.post("/api/v1/searches", headers=h, files={"image": ("a.jpg", image_bytes(), "image/jpeg")})).json()["id"]
        assert (await c.get("/api/v1/me", headers=h)).json()["quota"]["used"] == 1
        await pl.run_search(uuid.UUID(sid))
        s = (await c.get(f"/api/v1/searches/{sid}", headers=h)).json()
        assert s["status"] == "failed" and s["error"] == "ai_unavailable"
        assert (await c.get("/api/v1/me", headers=h)).json()["quota"]["used"] == 0


async def test_web_sources_fill_marketplaces_without_keys(pipeline_fakes: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Free plan: eBay (no keys) and Wildberries (no feed) are served by Google Vision web detection."""
    import uuid

    from pydantic import SecretStr

    import app.search.pipeline as pl
    from app.api.main import create_app
    from app.core.config import get_settings
    from app.marketplace import lens, registry
    from app.marketplace.providers.feed import WildberriesProvider

    s = get_settings()
    monkeypatch.setattr(s, "google_vision_api_key", SecretStr("test-key"))
    monkeypatch.setattr(s, "lens_provider", "google_vision")
    monkeypatch.setattr(s, "text_search_provider", "none")
    monkeypatch.setattr(pl.registry, "visible_providers", lambda: [p for p in registry.providers().values() if p.enabled])  # real registry

    async def fake_lens(q, codes: list[str], per: int):  # type: ignore[no-untyped-def]
        assert q.image_public_url and "/api/v1/media/" in q.image_public_url
        assert sorted(codes) == ["ebay", "wildberries"]  # aliexpress has no keys too, but stays outside: see below
        data = {"responses": [{"webDetection": {"pagesWithMatchingImages": [
            {"url": "https://www.ebay.com/itm/205123456789", "pageTitle": "Blue knit sweater", "fullMatchingImages": [{"url": "https://i.ebayimg.com/a.jpg"}]},
            {"url": "https://www.wildberries.ru/catalog/15342671/detail.aspx", "pageTitle": "Свитер синий", "partialMatchingImages": [{"url": "https://basket.wb.ru/b.jpg"}]},
        ]}}]}  # fmt: skip
        return lens.parse_web_detection(data, codes, per)

    monkeypatch.setattr(lens, "search_by_photo", fake_lens)
    monkeypatch.setattr(s, "web_search_marketplaces", ["ebay", "wildberries", "avito"])
    registry.providers.cache_clear()
    try:
        provs = registry.providers()
        assert provs["ebay"].info().kind.value == "web_search"
        assert provs["aliexpress"].info().state.value == "not_configured"  # not in WEB_SEARCH_MARKETPLACES
        assert provs["avito"].info().kind.value == "web_search"
        assert isinstance(provs["wildberries"], WildberriesProvider)

        app = create_app()
        h = {"Authorization": "tma " + init_data(300, "web")}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/api/v1/searches", headers=h, files={"image": ("a.jpg", image_bytes(), "image/jpeg")})
            sid = r.json()["id"]
            await pl.run_search(uuid.UUID(sid))
            st = (await c.get(f"/api/v1/searches/{sid}", headers=h)).json()
            assert st["status"] == "completed", st
            assert st["providers"]["ebay"]["state"] == "done" and st["providers"]["wildberries"]["state"] == "done"
            assert "avito" not in st["providers"]  # not in the free plan
            res = (await c.get(f"/api/v1/searches/{sid}/results", headers=h)).json()
            by = {i["marketplace"]: i for i in res["items"]}
            assert set(by) == {"ebay", "wildberries"}
            assert by["ebay"]["via"] == "google_lens" and by["ebay"]["similarity"] is not None  # real photo -> real %
            assert by["wildberries"]["url"] == "https://www.wildberries.ru/catalog/15342671/detail.aspx"
            cfg = (await c.get("/api/v1/config")).json()
            assert {m["code"]: m["kind"] for m in cfg["marketplaces"]}["ebay"] == "web_search"
    finally:
        registry.providers.cache_clear()


async def test_photo_search_survives_ai_outage(pipeline_fakes: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini down, no embeddings: Google Lens still finds listings; the search completes without a %."""
    import uuid

    from pydantic import SecretStr

    import app.search.pipeline as pl
    from app.ai.base import AIUnavailable
    from app.api.main import create_app
    from app.core.config import get_settings
    from app.marketplace import lens, registry

    class DeadVision(FakeVision):
        async def analyze(self, image_jpeg: bytes, *, deep: bool) -> ImageAnalysis:
            raise AIUnavailable("down")

    class NoEmb(FakeEmbedder):
        async def embed_images(self, images: list[bytes]) -> list[list[float]]:
            raise AIUnavailable("disabled")

    s = get_settings()
    monkeypatch.setattr(s, "lens_provider", "serper")
    monkeypatch.setattr(s, "serper_api_key", SecretStr("k"))
    monkeypatch.setattr(s, "text_search_provider", "none")
    monkeypatch.setattr(pl, "build_vision_analyzer", lambda: DeadVision())
    monkeypatch.setattr(pl, "build_embedding_provider", lambda: NoEmb())
    monkeypatch.setattr(pl.registry, "visible_providers", lambda: [p for p in registry.providers().values() if p.enabled])

    async def fake_lens(q, codes: list[str], per: int):  # type: ignore[no-untyped-def]
        data = {
            "organic": [{"link": "https://www.ebay.com/itm/205123456789", "title": "Sweater", "imageUrl": "https://i/1.jpg", "price": "$30"}]
        }  # noqa: E501
        return lens.parse_serper_lens(data, codes, per)

    monkeypatch.setattr(lens, "search_by_photo", fake_lens)
    registry.providers.cache_clear()
    try:
        h = {"Authorization": "tma " + init_data(301, "lens")}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t") as c:
            sid = (await c.post("/api/v1/searches", headers=h, files={"image": ("a.jpg", image_bytes(), "image/jpeg")})).json()["id"]
            await pl.run_search(uuid.UUID(sid))
            st = (await c.get(f"/api/v1/searches/{sid}", headers=h)).json()
            assert st["status"] == "completed" and not st["has_similarity"], st
            items = (await c.get(f"/api/v1/searches/{sid}/results", headers=h)).json()["items"]
            assert len(items) == 1 and items[0]["similarity"] is None and items[0]["price"] == "30.00"
            # the card shows the photo Lens found, served from our copy, with the remote URL as fallback
            it = items[0]
            assert it["image_url"].startswith("/api/v1/media/thumbs/") and it["image_fallback_url"] == "https://i/1.jpg"
            img = await c.get(it["image_url"])
            assert img.status_code == 200 and img.content == b"jpeg"
    finally:
        registry.providers.cache_clear()


async def test_gemini_verification_scores_and_hides_wrong_items(pipeline_fakes: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """No embeddings: Gemini compares photos, the % comes from it, clearly different items are hidden."""
    import uuid

    from pydantic import SecretStr

    import app.search.pipeline as pl
    from app.ai.verify import GeminiVerifier, Verdict
    from app.api.main import create_app
    from app.core.config import get_settings
    from app.marketplace import lens, registry

    class NoEmb(FakeEmbedder):
        model_id = "none"

    s = get_settings()
    monkeypatch.setattr(s, "lens_provider", "serper")
    monkeypatch.setattr(s, "serper_api_key", SecretStr("k"))
    monkeypatch.setattr(s, "text_search_provider", "none")
    monkeypatch.setattr(pl, "build_embedding_provider", lambda: NoEmb())
    monkeypatch.setattr(pl, "verify_ready", lambda: True)
    monkeypatch.setattr(pl.registry, "visible_providers", lambda: [p for p in registry.providers().values() if p.enabled])
    ids = [205123456781, 205123456782, 205123456783, 205123456784]

    async def fake_lens(q, codes: list[str], per: int):  # type: ignore[no-untyped-def]
        data = {"organic": [{"link": f"https://www.ebay.com/itm/{i}", "title": f"Item {i}", "imageUrl": f"https://i/{i}.jpg"} for i in ids]}
        return lens.parse_serper_lens(data, codes, per)

    seen: list[int] = []

    async def fake_verify(self, query: bytes, cands: list[bytes], hint: str | None = None):  # type: ignore[no-untyped-def]
        seen.append(len(cands))
        # stored thumbs hold b"jpeg" in this fixture, so score by position: Lens order 1..4
        return {0: Verdict(95, "same"), 1: Verdict(80, "same"), 2: Verdict(50, "similar"), 3: Verdict(10, "different")}

    monkeypatch.setattr(lens, "search_by_photo", fake_lens)
    monkeypatch.setattr(GeminiVerifier, "verify", fake_verify)
    registry.providers.cache_clear()
    try:
        h = {"Authorization": "tma " + init_data(302, "verify")}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t") as c:
            sid = (await c.post("/api/v1/searches", headers=h, files={"image": ("a.jpg", image_bytes(), "image/jpeg")})).json()["id"]
            await pl.run_search(uuid.UUID(sid))
            st = (await c.get(f"/api/v1/searches/{sid}", headers=h)).json()
            assert st["status"] == "completed" and st["has_similarity"] and st["results_count"] == 3, st
            items = (await c.get(f"/api/v1/searches/{sid}/results", headers=h)).json()["items"]
            assert [i["similarity"] for i in items] == [95, 80, 50] and seen == [4]
            assert items[0]["url"].endswith(str(ids[0]))
    finally:
        registry.providers.cache_clear()
