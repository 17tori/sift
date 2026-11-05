"""Web-backed sources: listing rules, Google Vision parsing, Claude web-search grounding, shared run."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.marketplace import lens, listing, web, websearch
from app.marketplace.base import ProviderError, SearchQuery


def test_listing_rules() -> None:
    assert listing.listing_id("avito", "https://www.avito.ru/moskva/odezhda/sviter_1234567890") == "1234567890"
    assert listing.listing_id("avito", "https://www.avito.ru/moskva/odezhda") is None
    assert listing.listing_id("vinted", "https://www.vinted.fr/items/4471234-pull-bleu") == "4471234"
    assert listing.listing_id("vinted", "https://www.vinted.fr/catalog?search_text=pull") is None
    assert listing.listing_id("wildberries", "https://www.wildberries.ru/catalog/15342671/detail.aspx") == "15342671"
    assert listing.listing_id("grailed", "https://www.grailed.com/listings/61234567-acne-sweater") == "61234567"
    assert listing.listing_id("ebay", "https://www.ebay.com/itm/205123456789") == "205123456789"
    assert listing.listing_id("aliexpress", "https://aliexpress.ru/item/1005006123456789.html") == "1005006123456789"
    assert listing.listing_id("taobao", "https://item.taobao.com/item.htm?spm=a&id=712345678901") == "712345678901"
    assert listing.source_for("https://m.avito.ru/x_123456", ["vinted", "avito"]) == "avito"
    assert listing.source_for("https://evil-avito.ru/x_123456", ["avito"]) is None
    assert listing.canonical("http://www.vinted.fr/items/1/") == listing.canonical("https://vinted.fr/items/1")
    assert listing.clean_title("<b>Свитер</b> &amp; шарф") == "Свитер & шарф"


VISION = {
    "responses": [
        {
            "webDetection": {
                "bestGuessLabels": [{"label": "acne studios sweater"}],
                "pagesWithMatchingImages": [
                    {"url": "https://www.vinted.fr/catalog?search_text=acne", "pageTitle": "search page",
                     "fullMatchingImages": [{"url": "https://img/a.jpg"}]},
                    {"url": "https://www.grailed.com/listings/61234567-acne", "pageTitle": "<b>Acne</b> sweater",
                     "partialMatchingImages": [{"url": "https://img/g.jpg"}]},
                    {"url": "https://www.vinted.fr/items/4471234-pull", "pageTitle": "Pull Acne",
                     "fullMatchingImages": [{"url": "https://img/v.jpg"}]},
                    {"url": "https://randomblog.com/post/1", "pageTitle": "blog",
                     "fullMatchingImages": [{"url": "https://img/b.jpg"}]},
                ],
            }
        }
    ]
}  # fmt: skip


def test_parse_web_detection_keeps_only_listings() -> None:
    found, labels = lens.parse_web_detection(VISION, ["vinted", "grailed", "avito"], 10)
    assert labels == ["acne studios sweater"]
    assert [p.url for p in found["vinted"]] == ["https://www.vinted.fr/items/4471234-pull"]
    assert found["vinted"][0].image_url == "https://img/v.jpg" and found["vinted"][0].raw["match"] == "full"
    assert found["grailed"][0].title == "Acne sweater" and found["grailed"][0].external_id == "web:61234567"
    assert found["avito"] == []
    with pytest.raises(ProviderError):
        lens.parse_web_detection({"responses": [{"error": {"message": "bad key"}}]}, ["vinted"], 5)


def _block(**kw):  # type: ignore[no-untyped-def]
    return SimpleNamespace(**kw)


def test_claude_web_search_rejects_ungrounded_urls() -> None:
    content = [
        _block(
            type="web_search_tool_result",
            content=[
                _block(type="web_search_result", url="https://www.avito.ru/moskva/odezhda/sviter_3001234567", title="Свитер", page_age="2 days"),
                _block(type="web_search_result", url="https://www.avito.ru/moskva/odezhda", title="Одежда", page_age=None),
            ],
        ),
        _block(
            type="text",
            text='Found.\n```json\n{"listings": ['
            '{"url": "https://avito.ru/moskva/odezhda/sviter_3001234567/", "title": "Синий свитер", "price": 2500, "currency": "rub"},'
            '{"url": "https://www.avito.ru/moskva/odezhda/sviter_9999999999", "title": "invented", "price": 1},'
            '{"url": "https://www.avito.ru/moskva/odezhda", "title": "category page"}'
            "]}\n```",
        ),
    ]
    out = websearch.build_products(content, ["avito"], 10)
    assert len(out["avito"]) == 1
    p = out["avito"][0]
    assert p.url == "https://www.avito.ru/moskva/odezhda/sviter_3001234567"  # the URL Google/Claude really returned
    assert p.price == 2500 and p.currency == "RUB" and p.image_url is None and p.raw["via"] == "web_search"


def _q() -> SearchQuery:
    return SearchQuery(texts={"ru": ["синий свитер"]}, image_jpeg=b"jpeg", query_embedding=None, embedding_model=None,
                       category="knitwear", gender=None, limit=5)  # fmt: skip


async def test_one_shared_run_per_search(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def fake_lens(q: SearchQuery, codes: list[str], per: int):  # type: ignore[no-untyped-def]
        calls.append(codes)
        await asyncio.sleep(0.01)
        return lens.parse_web_detection(VISION, codes, per)

    class FakeHub:
        async def run(self, q, codes, hints):  # type: ignore[no-untyped-def]
            assert hints == ["acne studios sweater"]
            return {c: [] for c in codes}

    monkeypatch.setattr(lens, "lens_ready", lambda: True)
    monkeypatch.setattr(lens, "search_by_photo", fake_lens)
    monkeypatch.setattr(websearch, "web_search_ready", lambda: True)
    monkeypatch.setattr(websearch, "hub", lambda: FakeHub())
    q = _q()
    q.shared["web_codes"] = ["vinted", "grailed"]
    v, g = await asyncio.gather(web.search_for("vinted", q), web.search_for("grailed", q))
    assert len(calls) == 1 and len(v) == 1 and len(g) == 1


async def test_web_run_fails_only_when_every_channel_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_lens(*a):  # type: ignore[no-untyped-def]
        raise ProviderError("vision HTTP 403")

    class EmptyHub:
        async def run(self, q, codes, hints):  # type: ignore[no-untyped-def]
            return {c: [] for c in codes}

    monkeypatch.setattr(lens, "lens_ready", lambda: True)
    monkeypatch.setattr(lens, "search_by_photo", broken_lens)
    monkeypatch.setattr(websearch, "web_search_ready", lambda: True)
    monkeypatch.setattr(websearch, "hub", lambda: EmptyHub())
    assert await web.search_for("vinted", _q()) == []  # one channel answered: honest empty result
    monkeypatch.setattr(websearch, "web_search_ready", lambda: False)
    with pytest.raises(ProviderError):
        await web.search_for("vinted", _q())


def test_parse_serper_lens() -> None:
    data = {
        "organic": [
            {"title": "Pullover blau", "source": "Vinted", "link": "https://www.vinted.de/items/555123-pullover",
             "imageUrl": "https://img/v.jpg", "thumbnailUrl": "https://t/v.jpg", "price": "€25,00"},
            {"title": "Свитер", "source": "Авито", "link": "https://www.avito.ru/moskva/odezhda/sviter_3009876543",
             "thumbnailUrl": "https://img/a.jpg", "price": "2 500 ₽", "inStock": False},
            {"title": "pin", "link": "https://www.pinterest.com/pin/1"},
            {"title": "profile", "link": "https://www.vinted.de/member/1-bob"},
        ]
    }  # fmt: skip
    found, _ = lens.parse_serper_lens(data, ["vinted", "avito"], 10)
    v, a = found["vinted"][0], found["avito"][0]
    assert len(found["vinted"]) == 1 and v.price == 25 and v.currency == "EUR" and v.image_url == "https://img/v.jpg"
    assert a.price == 2500 and a.currency == "RUB" and a.available is False and a.image_url == "https://img/a.jpg"
    with pytest.raises(ProviderError):
        lens.parse_serper_lens({"message": "Unauthorized."}, ["vinted"], 5)


def test_price_strings() -> None:
    assert lens.parse_price("$25.99") == (Decimal("25.99"), "USD")
    assert lens.parse_price("1.299,50 €")[0] == 1299.5 and lens.parse_price("12,990 руб.")[0] == 12990
    assert lens.parse_price("25") == (None, None)  # no currency -> no price, never guessed


def test_serp_google_organic_results() -> None:
    from app.marketplace import serptext

    data = {
        "organic": [
            {"link": "https://www.avito.ru/spb/odezhda/sviter_3001112223", "title": "Свитер Acne Studios",
             "attributes": {"Цена": "4 900 ₽"}},
            {"link": "https://www.avito.ru/spb/odezhda", "title": "Одежда в СПб"},
            {"link": "https://www.wildberries.ru/catalog/15342671/detail.aspx", "title": "Свитер", "imageUrl": "https://t/w.jpg"},
        ]
    }  # fmt: skip
    out = serptext.parse_organic(data, ["avito", "wildberries"], 10)
    assert [p.price for p in out["avito"]] == [4900] and out["avito"][0].currency == "RUB"
    assert out["wildberries"][0].image_url == "https://t/w.jpg" and out["wildberries"][0].raw["via"] == "web_search"
    assert serptext._query("синий свитер", ["avito", "wildberries"]) == "синий свитер (site:avito.ru OR site:wildberries.ru)"


def test_gemini_response_parsing() -> None:
    import json

    from app.ai.base import AIUnavailable
    from app.ai.vision import parse_gemini

    analysis = {
        "is_product": True, "rejection_reason": None, "category": "knitwear", "subcategory": "sweater",
        "title_en": "Blue sweater", "title_ru": "Синий свитер", "gender": "unisex",
        "colors": [{"name": "blue", "hex": "#1e3cc8"}], "material": "wool", "pattern": None, "silhouette": None,
        "style": [], "features": [], "brand": {"name": None, "confidence": "none", "evidence": None},
        "queries": {"en": ["blue sweater"], "ru": ["синий свитер"], "zh": []},
        "discover_queries": {"en": [], "ru": [], "zh": []},
    }  # fmt: skip
    ok = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(analysis)}]}}]}
    assert parse_gemini(ok).title_ru == "Синий свитер"
    with pytest.raises(AIUnavailable):
        parse_gemini({"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(AIUnavailable):
        parse_gemini({"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]})


def test_serper_images_fill_missing_photos() -> None:
    from app.marketplace import serptext

    organic = {
        "organic": [
            {"link": "https://www.avito.ru/moskva/odezhda/sviter_1234567890", "title": "Свитер - Авито"},
            {"link": "https://www.grailed.com/listings/555111", "title": "Sweater", "imageUrl": "https://g/own.jpg"},
        ]
    }
    images = {
        "images": [
            {"link": "https://www.avito.ru/moskva/odezhda/sviter_1234567890?utm=x", "imageUrl": "https://00.img.avito.st/1.jpg",
             "thumbnailUrl": "https://encrypted-tbn0.gstatic.com/a", "title": "Свитер"},
            {"link": "https://www.grailed.com/listings/555111", "imageUrl": "https://g/other.jpg"},
            {"link": "https://www.grailed.com/listings/777222", "imageUrl": "https://g/new.jpg", "title": "Knit"},
            {"link": "https://www.grailed.com/designers/acne", "imageUrl": "https://g/cat.jpg"},
            {"link": "https://example.com/p/1", "imageUrl": "https://x/1.jpg"},
        ]
    }  # fmt: skip
    codes = ["avito", "grailed"]
    found = serptext.parse_organic(organic, codes, 10)
    serptext.attach_images(found, serptext.parse_images(images, codes), 10)
    av = found["avito"][0]
    assert av.image_url == "https://00.img.avito.st/1.jpg" and av.raw["image_alt"] == "https://encrypted-tbn0.gstatic.com/a"
    gr = {p.url: p for p in found["grailed"]}
    assert gr["https://www.grailed.com/listings/555111"].image_url == "https://g/own.jpg"  # own photo kept
    added = gr["https://www.grailed.com/listings/777222"]
    assert added.image_url == "https://g/new.jpg" and added.raw["engine"] == "google_images" and added.price is None
    assert len(found["grailed"]) == 2  # category page and foreign domain skipped


async def test_thumbs_stored_once_and_refetched_on_change(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from decimal import Decimal

    from app.db.session import session_scope
    from app.marketplace.base import NormalizedProduct
    from app.services import thumbs
    from app.services.catalog import upsert_products

    calls: list[list[str]] = []

    async def fake_fetch(urls: list[str], concurrency: int = 12) -> dict[str, bytes]:
        calls.append(list(urls))
        return {u: b"img:" + u.encode() for u in urls if "dead" not in u}

    monkeypatch.setattr(thumbs, "fetch_many", fake_fetch)

    def item(img: str, alt: str | None = None) -> NormalizedProduct:
        return NormalizedProduct(source="ebay", external_id="web:9988776655", title="t", url="https://www.ebay.com/itm/9988776655",
                                 image_url=img, price=Decimal(1), currency="USD", raw={"image_alt": alt} if alt else {})  # fmt: skip

    async def ingest(p: NormalizedProduct) -> tuple[int, dict[int, bytes]]:
        async with session_scope() as s:
            pid = (await upsert_products(s, [p]))[(p.source, p.external_id)]
        return pid, await thumbs.ensure_thumbs([(pid, p)])

    pid, got = await ingest(item("https://cdn/dead.jpg", "https://tbn/alt.jpg"))
    assert got[pid] == b"img:https://tbn/alt.jpg"  # CDN refused -> Google thumbnail
    key1, src1 = (await thumbs.thumb_state([pid]))[pid]
    assert key1 and src1 == "https://cdn/dead.jpg"
    n = len(calls)
    _, got = await ingest(item("https://cdn/dead.jpg", "https://tbn/alt.jpg"))
    assert got == {} and len(calls) == n  # same photo URL: no refetch
    _, got = await ingest(item("https://cdn/new.jpg"))
    key2, _ = (await thumbs.thumb_state([pid]))[pid]
    assert key2 != key1 and (await thumbs.read_thumbs({pid: key2}))[pid] == b"img:https://cdn/new.jpg"
    assert await thumbs.read_thumbs({pid: key1}) == {}  # old copy removed


def test_avito_listing_with_tracking_params() -> None:
    assert listing.listing_id("avito", "https://www.avito.ru/moskva/odezhda/sviter_1234567890?context=abc") == "1234567890"
    assert listing.listing_id("avito", "https://www.avito.ru/moskva/odezhda?q=sviter_1234567") is None


def test_gemini_verify_parsing_and_body() -> None:
    from app.ai.base import AIUnavailable
    from app.ai.verify import build_body, parse_verdicts

    body = build_body(b"q", [b"a", b"b"], "blue knit sweater")
    parts = body["contents"][0]["parts"]
    texts = [p.get("text") for p in parts if "text" in p]
    assert texts == ["Image 0 (user's photo) — blue knit sweater:", "#1:", "#2:", "Score listings #1..#2."]
    assert body["generationConfig"]["responseJsonSchema"]["required"] == ["items"]
    items = '[{"i":1,"score":120,"verdict":"same"},{"i":2,"score":12,"verdict":"different"},{"i":7,"score":50,"verdict":"similar"},{"i":"x"}]'
    text = '```json\n{"items":' + items + "}\n```"
    data = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"thought": True, "text": "hmm"}, {"text": text}]}}]}
    v = parse_verdicts(data, 2)
    assert v[0].score == 100 and v[0].verdict == "same" and v[1].score == 12 and set(v) == {0, 1}
    with pytest.raises(AIUnavailable):
        parse_verdicts({"candidates": [{"finishReason": "SAFETY"}]}, 2)
