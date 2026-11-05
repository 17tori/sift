"""Marketplaces without a legal third-party search integration (researched 2026-11).

They stay visible in the UI with an honest status. If a partnership or licensed data feed
becomes available, switch the provider to `FeedCatalogProvider` (see wildberries.py) or
implement the official API in a new class with the same interface.
"""

from __future__ import annotations

from app.marketplace.base import NoLegalApiProvider


class AvitoProvider(NoLegalApiProvider):
    code = "avito"
    name = "Avito"
    url = "https://www.avito.ru"
    regions = ["RU"]
    languages = ("ru",)
    note = (
        "Официальный Avito API (developers.avito.ru) даёт доступ только к своим объявлениям, "
        "мессенджеру и автозагрузке. Поиска по чужим объявлениям в API нет; парсинг сайта "
        "запрещён правилами площадки. Нужен партнёрский договор или лицензированный фид."
    )


class VintedProvider(NoLegalApiProvider):
    code = "vinted"
    name = "Vinted"
    url = "https://www.vinted.com"
    regions = ["EU", "UK", "US"]
    note = (
        "У Vinted нет публичного API поиска. Vinted Pro Integrations рассчитан на продавцов "
        "(управление своими товарами). Требуется прямое партнёрство с Vinted."
    )


class GrailedProvider(NoLegalApiProvider):
    code = "grailed"
    name = "Grailed"
    url = "https://www.grailed.com"
    regions = ["US", "EU"]
    note = "Публичного API у Grailed нет; внутренние эндпоинты сайта не предназначены для сторонних сервисов. Требуется партнёрство с Grailed."


class GoofishProvider(NoLegalApiProvider):
    code = "goofish"
    name = "Goofish (闲鱼)"
    url = "https://www.goofish.com"
    regions = ["CN"]
    languages = ("zh",)
    note = (
        "Открытая платформа Goofish рассчитана на продавцов (публикация и управление своими "
        "лотами); API поиска по чужим объявлениям нет. Отключено в конфигурации."
    )
