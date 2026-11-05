"""Price comparison, item screen, collections, watches, shared finds, gift searches."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.db.models import Product, SearchResult, SearchSession, User, Watch
from app.db.session import session_scope
from app.services import gifts, payments, shares, subscriptions, watches
from app.services.users import TelegramIdentity, get_or_create_user
from tests.helpers import image_bytes, init_data

pytestmark = pytest.mark.usefixtures("db")


def auth(tg: int, start: str | None = None) -> dict[str, str]:
    return {"Authorization": "tma " + init_data(tg, f"u{tg}", start_param=start)}


async def make_search(
    tg: int, items: list[tuple[str, str, Decimal | None, int | None]], plan: str | None = None
) -> tuple[int, uuid.UUID, list[int]]:
    """items: (source, external id, price RUB, similarity). Returns (user id, search id, product ids)."""
    async with session_scope() as s:
        user, _ = await get_or_create_user(s, TelegramIdentity(tg, f"u{tg}", "Ann", None, "ru"))
        if plan:
            await subscriptions.grant(s, user.id, plan, 30, "admin")
        srch = SearchSession(
            user_id=user.id, status="completed", stage="done", mode="similar", image_key="uploads/x.jpg", image_hash="h",
            image_width=10, image_height=10, options={}, providers_status={}, analysis={"title_ru": "Синий свитер"},
        )  # fmt: skip
        s.add(srch)
        await s.flush()
        pids = []
        for rank, (src, ext, price, sim) in enumerate(items):
            p = Product(source=src, external_id=f"{tg}-{ext}", title=f"{src} {ext}", url=f"https://{src}.example/{ext}", image_url=None,
                        price=price, currency="RUB" if price is not None else None, raw={})  # fmt: skip
            s.add(p)
            await s.flush()
            s.add(SearchResult(search_id=srch.id, product_id=p.id, provider=src, similarity_pct=sim, cosine=(sim or 0) / 100,
                               text_rank=rank, rank_score=1 - rank / 10))  # fmt: skip
            pids.append(p.id)
        return user.id, srch.id, pids


def client() -> httpx.AsyncClient:
    from app.api.main import create_app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t")


async def test_price_range_and_item_screen() -> None:
    _, sid, pids = await make_search(
        501,
        [
            ("avito", "a1", Decimal("2400"), 92),
            ("ebay", "e1", Decimal("6900"), 88),
            ("grailed", "g1", Decimal("5000"), 75),
            ("avito", "a2", Decimal("1000"), 50),  # only similar: not the same item
            ("ebay", "e2", None, 95),  # same item but no price
        ],
    )
    async with client() as c:
        res = (await c.get(f"/api/v1/searches/{sid}/results", headers=auth(501))).json()
        rng = res["price_range"]
        assert rng["count"] == 3 and rng["marketplaces"] == 3
        assert rng["min"]["price"] == "2400.00" and rng["min"]["marketplace"] == "avito" and rng["max"]["price"] == "6900.00"
        it = (await c.get(f"/api/v1/searches/{sid}/items/{pids[0]}", headers=auth(501))).json()
        assert [o["product_id"] for o in it["offers"]] == [pids[2], pids[1]]  # same item elsewhere, cheapest first
        assert {s["product_id"] for s in it["similar"]} == {pids[3], pids[4]}
        assert it["favorite_id"] is None and not it["watching"]
        assert (await c.get(f"/api/v1/searches/{sid}/items/{pids[0]}", headers=auth(502))).status_code == 404


async def test_no_price_range_on_one_marketplace() -> None:
    _, sid, _ = await make_search(503, [("avito", "a1", Decimal("2400"), 92), ("avito", "a2", Decimal("2600"), 90)])
    async with client() as c:
        assert (await c.get(f"/api/v1/searches/{sid}/results", headers=auth(503))).json()["price_range"] is None


async def test_collections() -> None:
    _, sid, pids = await make_search(504, [("avito", "a1", Decimal("100"), 90), ("ebay", "e1", Decimal("200"), 80)])
    h = auth(504)
    async with client() as c:
        fav = (await c.post("/api/v1/favorites", headers=h, json={"product_id": pids[0], "search_id": str(sid)})).json()
        col = (await c.post("/api/v1/collections", headers=h, json={"title": "Зима"})).json()
        assert (await c.put(f"/api/v1/favorites/{fav['id']}/collection", headers=h, json={"collection_id": col["id"]})).status_code == 204
        cols = (await c.get("/api/v1/collections", headers=h)).json()
        assert cols == [{"id": col["id"], "title": "Зима", "count": 1, "cover_url": None}]
        favs = (await c.get("/api/v1/favorites", headers=h)).json()
        assert favs[0]["collection_id"] == col["id"]
        other = (await c.post("/api/v1/collections", headers=auth(505), json={"title": "Чужая"})).json()
        r = await c.put(f"/api/v1/favorites/{fav['id']}/collection", headers=h, json={"collection_id": other["id"]})
        assert r.status_code == 404
        assert (await c.delete(f"/api/v1/collections/{col['id']}", headers=h)).status_code == 204
        assert (await c.get("/api/v1/favorites", headers=h)).json()[0]["collection_id"] is None


async def test_watch_is_ultra_and_notifies_cheaper_and_new() -> None:
    _, sid, _ = await make_search(506, [("avito", "a1", Decimal("3000"), 92), ("ebay", "e1", Decimal("5000"), 85)])
    async with client() as c:
        r = await c.post("/api/v1/watches", headers=auth(506), json={"search_id": str(sid)})
        assert r.status_code == 403 and r.json()["error"]["code"] == "feature_locked"
    uid, sid, pids = await make_search(507, [("avito", "a1", Decimal("3000"), 92), ("ebay", "e1", Decimal("5000"), 85)], plan="ultra")
    async with client() as c:
        w = (await c.post("/api/v1/watches", headers=auth(507), json={"search_id": str(sid)})).json()
        assert w["best_price"] == "3000.00" and w["best_currency"] == "RUB"
        lst = (await c.get("/api/v1/watches", headers=auth(507))).json()
        assert lst["limit"] == 20 and len(lst["items"]) == 1
    # a re-run finds the same item cheaper on a new marketplace
    async with session_scope() as s:
        rerun = SearchSession(user_id=uid, status="completed", stage="done", mode="similar", image_key="uploads/x.jpg", image_hash="h",
                              image_width=10, image_height=10, options={"watch_id": w["id"]}, providers_status={}, hidden=True,
                              quota_counted=False)  # fmt: skip
        s.add(rerun)
        await s.flush()
        cheap = Product(source="grailed", external_id="g9", title="cheap", url="https://g/9", image_url=None, price=Decimal("2500"),
                        currency="RUB", raw={})  # fmt: skip
        s.add(cheap)
        await s.flush()
        for pid, sim in ((pids[0], 92), (cheap.id, 90)):
            s.add(SearchResult(search_id=rerun.id, product_id=pid, provider="x", similarity_pct=sim, text_rank=0, rank_score=1))
        rid = rerun.id
    text = await watches.evaluate(w["id"], rid)
    assert text and "Дешевле: <b>2 500 ₽</b>" in text and "было 3 000 ₽" in text and "Новые предложения: 1" in text
    assert await watches.evaluate(w["id"], rid) is None  # nothing new the second time
    async with session_scope() as s:
        ww = await s.get(Watch, w["id"])
        assert ww is not None and ww.best_price == Decimal("2500.00") and ww.runs == 2
    async with client() as c:
        assert (await c.get(f"/api/v1/searches/{rid}/results", headers=auth(507))).status_code == 200  # hidden re-run opens
        assert (await c.delete(f"/api/v1/watches/by-search/{sid}", headers=auth(507))).status_code == 204
        assert (await c.get("/api/v1/watches", headers=auth(507))).json()["items"] == []


async def test_share_card_link_and_referral(monkeypatch: pytest.MonkeyPatch) -> None:
    _, sid, pids = await make_search(508, [("grailed", "g1", Decimal("24500"), 92)])
    calls: list[dict[str, Any]] = []

    class Bot:
        async def save_prepared_inline_message(self, **kw: Any) -> Any:
            calls.append(kw)
            return type("P", (), {"id": "prep-1"})()

    async def no_photo(url: str, side: int = 384) -> None:
        return None

    monkeypatch.setattr(shares, "get_bot", lambda: Bot())
    monkeypatch.setattr(shares, "fetch_one", no_photo)
    async with client() as c:
        r = await c.post("/api/v1/shares", headers=auth(508), json={"product_id": pids[0], "search_id": str(sid)})
        assert r.status_code == 201, r.text
        sh = r.json()
        assert sh["prepared_message_id"] == "prep-1" and sh["link"].endswith(f"/app?startapp=f_{sh['token']}")
        assert calls[0]["result"].photo_url.endswith(f"/api/v1/shares/{sh['token']}/card.jpg")
        card = await c.get(f"/api/v1/shares/{sh['token']}/card.jpg")  # public, Telegram fetches it
        assert card.status_code == 200 and card.content[:2] == b"\xff\xd8"
        again = (await c.post("/api/v1/shares", headers=auth(508), json={"product_id": pids[0]})).json()
        assert again["token"] == sh["token"]
        # someone else cannot share a product that is not in their results
        assert (await c.post("/api/v1/shares", headers=auth(509), json={"product_id": pids[0]})).status_code == 403
        # a new user opening the find: sees it and is attributed to the sharer
        seen = (await c.get(f"/api/v1/shares/{sh['token']}", headers=auth(510, start=f"f_{sh['token']}"))).json()
        assert seen["sharer_name"] == "Ann" and seen["product"]["title"] == "grailed g1" and seen["search_id"] is None
    async with session_scope() as s:
        sharer = await s.scalar(select(User).where(User.telegram_id == 508))
        newbie = await s.scalar(select(User).where(User.telegram_id == 510))
        assert sharer is not None and newbie is not None and newbie.referred_by_id == sharer.id


async def test_gift_purchase_and_redeem(monkeypatch: pytest.MonkeyPatch) -> None:
    class Bot:
        async def create_invoice_link(self, **kw: Any) -> str:
            return f"https://t.me/$invoice_{kw['payload']}"

    monkeypatch.setattr(gifts, "get_bot", lambda: Bot())
    async with client() as c:
        packs = (await c.get("/api/v1/gifts/packs")).json()
        assert packs[0] == {"code": "g5", "searches": 5, "stars": 49}
        inv = (await c.post("/api/v1/gifts/invoice", headers=auth(520), json={"pack": "g20"})).json()
        assert inv["amount_stars"] == 149
    async with session_scope() as s:
        from app.db.models import PaymentIntent

        intent = await s.get(PaymentIntent, uuid.UUID(inv["intent_id"]))
        assert intent is not None and intent.kind == "gift"
        verdict = await payments.validate_pre_checkout(s, 520, intent.payload, "XTR", 149)
        assert verdict.ok
        payload = intent.payload
    kw = dict(telegram_user_id=520, payload=payload, currency="XTR", total_amount=149, provider_payment_charge_id=None,
              is_recurring=False, is_first_recurring=False, subscription_expiration_date=None, raw={})  # fmt: skip
    async with session_scope() as s:
        out = await payments.process_successful_payment(s, telegram_payment_charge_id="gift-1", **kw)
        assert out.gift is not None and out.gift.searches == 20 and out.subscription is None
        code = out.gift.code
    async with session_scope() as s:
        dup = await payments.process_successful_payment(s, telegram_payment_charge_id="gift-1", **kw)
        assert dup.duplicate
    async with client() as c:
        own = await c.post(f"/api/v1/gifts/{code}/redeem", headers=auth(520))
        assert own.status_code == 400 and own.json()["error"]["code"] == "gift_own"
        ok = (await c.post(f"/api/v1/gifts/{code}/redeem", headers=auth(521, start=f"g_{code}"))).json()
        assert ok == {"searches": 20, "from_name": "Test"}
        assert (await c.post(f"/api/v1/gifts/{code}/redeem", headers=auth(522))).json()["error"]["code"] == "gift_used"
        me = (await c.get("/api/v1/me", headers=auth(521))).json()
        assert me["quota"]["bonus"] >= 20
        mine = (await c.get("/api/v1/gifts", headers=auth(520))).json()
        assert mine[0]["status"] == "redeemed" and mine[0]["link"].endswith(f"startapp=g_{code}")


def test_postcard_renders_without_photo() -> None:
    from app.services import postcard

    data = postcard.render(postcard.CardData(title="Сумка", marketplace="Avito", price=None, number=1, photo=image_bytes(), footer="x"))
    assert data[:2] == b"\xff\xd8" and len(data) > 10_000
    assert shares.format_price(Decimal("2400"), "RUB") == "2 400 ₽" and shares.format_price(Decimal("25.99"), "USD") == "$25.99"
