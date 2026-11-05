"""Approximate currency conversion for cross-marketplace price sorting.

Source: Central Bank of Russia daily rates (official, free): https://www.cbr.ru/scripts/XML_daily.asp
Rates are stored as "RUB per 1 unit". Original prices are always shown; converted ones are
labelled approximate in the UI.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from decimal import Decimal

import httpx
import orjson

from app.core.redis import get_redis

log = logging.getLogger(__name__)
KEY = "fx:rub_per_unit"
CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp"


async def refresh() -> int:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(CBR_URL)
        r.raise_for_status()
    root = ET.fromstring(r.content)  # noqa: S314 - official CBR endpoint
    rates: dict[str, str] = {"RUB": "1"}
    for v in root.findall("Valute"):
        code = v.findtext("CharCode")
        nominal = Decimal((v.findtext("Nominal") or "1").replace(",", "."))
        value = Decimal((v.findtext("Value") or "0").replace(",", "."))
        if code and value > 0:
            rates[code] = str(value / nominal)
    await get_redis().set(KEY, orjson.dumps(rates), ex=3 * 86400)
    return len(rates)


async def rates() -> dict[str, Decimal]:
    raw = await get_redis().get(KEY)
    if not raw:
        return {}
    return {k: Decimal(v) for k, v in orjson.loads(raw).items()}


def convert(amount: Decimal | None, src: str | None, dst: str, table: dict[str, Decimal]) -> Decimal | None:
    if amount is None or not src:
        return None
    if src == dst:
        return amount
    a, b = table.get(src), table.get(dst)
    if a is None or b is None:
        return None
    return (amount * a / b).quantize(Decimal("0.01"))
