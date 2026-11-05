from __future__ import annotations

import time
from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.core.security import InitDataError, validate_init_data
from app.marketplace.base import ProviderUnavailable, SearchQuery
from app.marketplace.providers.aliexpress import AliExpressProvider, sign_iop
from app.marketplace.providers.ebay import EbayProvider
from app.marketplace.providers.taobao import TaobaoProvider, sign_top_md5
from app.marketplace.providers.unavailable import AvitoProvider, GoofishProvider
from app.marketplace.registry import providers, visible_providers
from app.search.ranking import Candidate, calibrate, mark_duplicates, score
from app.services import images
from tests.helpers import image_bytes, init_data

TOKEN = "123456:TEST-TOKEN"


def test_init_data_valid() -> None:
    d = validate_init_data(init_data(42, start_param="ref_ABCD1234"), TOKEN, 3600)
    assert d.user.id == 42 and d.user.username == "tester" and d.start_param == "ref_ABCD1234"


def test_init_data_tampered() -> None:
    raw = init_data(42).replace("tester", "hacker")
    with pytest.raises(InitDataError):
        validate_init_data(raw, TOKEN, 3600)


def test_init_data_wrong_token_and_expired() -> None:
    with pytest.raises(InitDataError):
        validate_init_data(init_data(1), "other:token", 3600)
    with pytest.raises(InitDataError):
        validate_init_data(init_data(1, auth_date=int(time.time()) - 7200), TOKEN, 3600)


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_image_normalize_formats(fmt: str) -> None:
    n = images.normalize(image_bytes(fmt), max_bytes=10_000_000, max_pixels=40_000_000, max_side=256)
    assert n.mime == "image/jpeg" and max(n.width, n.height) == 256 and len(n.dhash) == 16
    assert n.data[:3] == b"\xff\xd8\xff"


def test_image_rejects() -> None:
    with pytest.raises(AppError) as e:
        images.normalize(b"GIF89a....", max_bytes=10_000, max_pixels=1_000_000, max_side=256)
    assert e.value.code == "image_format"
    with pytest.raises(AppError) as e:
        images.normalize(image_bytes(), max_bytes=100, max_pixels=1_000_000, max_side=256)
    assert e.value.code == "image_too_large"
    with pytest.raises(AppError) as e:
        images.normalize(image_bytes(size=(40, 40)), max_bytes=10_000_000, max_pixels=1_000_000, max_side=256)
    assert e.value.code == "image_too_small"
    with pytest.raises(AppError) as e:
        images.normalize(b"\xff\xd8\xff" + b"garbage" * 10, max_bytes=10_000_000, max_pixels=1_000_000, max_side=256)
    assert e.value.code == "image_invalid"


def test_dhash_stable() -> None:
    a = images.normalize(image_bytes(), max_bytes=10**7, max_pixels=10**8, max_side=512)
    b = images.normalize(image_bytes("PNG"), max_bytes=10**7, max_pixels=10**8, max_side=512)
    assert bin(int(a.dhash, 16) ^ int(b.dhash, 16)).count("1") <= 6  # JPEG vs PNG source


def test_calibration() -> None:
    assert calibrate(0.2, 0.55, 0.93) == 0
    assert calibrate(0.99, 0.55, 0.93) == 100
    assert calibrate(0.74, 0.55, 0.93) == 50


def test_ranking_never_promotes_unscored_above_real_match() -> None:
    real = Candidate(1, "ebay", 10, 0.5, Decimal("10"), None, "a")
    unscored = Candidate(2, "ebay", 0, None, Decimal("10"), None, "b")
    assert score(real, "similar", None) > score(unscored, "similar", None)


def test_cheaper_mode_penalises_expensive() -> None:
    cheap = Candidate(1, "ebay", 0, 0.8, Decimal("50"), None, "a")
    pricey = Candidate(2, "ebay", 0, 0.8, Decimal("150"), None, "b")
    assert score(cheap, "cheaper", Decimal("100")) > score(pricey, "cheaper", Decimal("100"))


def test_duplicates() -> None:
    v = [1.0, 0.0, 0.0]
    a = Candidate(1, "ebay", 0, 0.9, Decimal("10"), "http://x/1.jpg", "Black bag", embedding=v)
    b = Candidate(2, "ebay", 1, 0.9, Decimal("11"), "http://x/1.jpg", "Black bag", embedding=v)
    c = Candidate(3, "ebay", 2, 0.9, Decimal("12"), "http://x/2.jpg", "black   BAG!", embedding=v)
    d = Candidate(4, "aliexpress", 0, 0.9, Decimal("5"), "http://y/9.jpg", "Black bag", embedding=v)
    mark_duplicates([a, b, c, d], threshold=0.98)
    assert [x.duplicate for x in (a, b, c, d)] == [False, True, True, False]  # cross-marketplace kept


def test_signatures_deterministic() -> None:
    p = {"method": "x", "app_key": "1", "timestamp": "2"}
    assert sign_iop(p, "s") == sign_iop(dict(reversed(list(p.items()))), "s")
    assert len(sign_iop(p, "s")) == 64 and sign_iop(p, "s").isupper()
    assert len(sign_top_md5(p, "s")) == 32


def test_ebay_normalize() -> None:
    raw = {
        "itemId": "v1|123|0",
        "title": "Black leather bag",
        "price": {"value": "45.50", "currency": "USD"},
        "image": {"imageUrl": "https://i.ebayimg.com/x.jpg"},
        "itemWebUrl": "https://www.ebay.com/itm/123",
        "conditionId": "3000",
        "seller": {"username": "s1"},
        "itemLocation": {"country": "US"},
    }
    p = EbayProvider(True).normalize_product(raw)
    assert p and p.price == Decimal("45.50") and p.condition == "used" and p.country == "US"
    assert EbayProvider(True).normalize_product({"title": "no id"}) is None


def test_aliexpress_taobao_normalize() -> None:
    a = AliExpressProvider(True).normalize_product(
        {
            "product_id": 1005,
            "product_title": "Bag",
            "promotion_link": "https://s.click.aliexpress.com/e/x",
            "product_main_image_url": "https://ae01/x.jpg",
            "target_sale_price": "12.30",
            "target_sale_price_currency": "USD",
        }
    )
    assert a and a.price == Decimal("12.30") and a.url.startswith("https://s.click")
    t = TaobaoProvider(True).normalize_product(
        {
            "item_id": "abc",
            "item_basic_info": {"title": "包", "pict_url": "//img.alicdn.com/x.jpg"},
            "price_promotion_info": {"zk_final_price": "88.00"},
            "publish_info": {"click_url": "//s.click.taobao.com/t"},
        }
    )
    assert t and t.image_url == "https://img.alicdn.com/x.jpg" and t.currency == "CNY"


async def test_unavailable_providers_never_return_data() -> None:
    q = SearchQuery(texts={"ru": ["сумка"]}, image_jpeg=None, query_embedding=None, embedding_model=None, category=None, gender=None)
    for p in (AvitoProvider(True), GoofishProvider(True)):
        with pytest.raises(ProviderUnavailable):
            await p.search(q)
    # unconfigured real integration refuses too (no fake fallback)
    with pytest.raises(ProviderUnavailable):
        await EbayProvider(True).search(q)


def test_goofish_disabled_by_default() -> None:
    assert providers()["goofish"].enabled is False
    assert "goofish" not in {p.code for p in visible_providers()}


def test_settings_csv_env(monkeypatch) -> None:
    from app.core.config import Settings

    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "")
    monkeypatch.setenv("MARKETPLACES_ENABLED", "ebay, vinted")
    s = Settings(_env_file=None)
    assert s.admin_telegram_ids == [] and s.marketplaces_enabled == ["ebay", "vinted"]
    monkeypatch.setenv("ADMIN_TELEGRAM_IDS", "1,2")
    assert Settings(_env_file=None).admin_telegram_ids == [1, 2]
