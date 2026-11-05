# Маркетплейсы: что подключено и как

Правило проекта: **только легальные источники.** Никакого парсинга сайтов, обхода CAPTCHA, авторизации или
антибот-защиты, никаких выдуманных результатов. Площадка без легального доступа честно отображается в
приложении как «нет официального API» и ничего не возвращает.

## Как SIFT ищет без партнёрских ключей

Пока ключей площадки нет (или у неё вообще нет API), SIFT подключает её через **веб-источники**. Ни один из них
не обращается к сайту площадки, поэтому ничего не парсится и защита площадок не затрагивается:

1. **Поиск по фото, Google Lens.** Фото отправляется в Lens, и в ответ приходят страницы с такой же или похожей
   вещью. SIFT оставляет только страницы конкретных товаров на известных площадках и раскладывает их по маркетплейсам.
   - `LENS_PROVIDER=serper` (по умолчанию): Google Lens через [serper.dev](https://serper.dev). Выдача как
     в приложении Lens: товары с фото и часто с ценой. **Важно:** serper.dev не официальный API Google, сервис сам
     получает выдачу Google. Площадки при этом не затрагиваются, но это решение
     владельца продукта.
   - `LENS_PROVIDER=google_vision`: официальный Google Cloud Vision API (Web Detection). Полностью легально,
     около $3.5 за 1000 поисков, но находит заметно меньше товаров, чем Lens.
2. **Поиск по описанию.** Фразы из анализа фото (Gemini) и метка Lens ищутся в Google только по доменам площадок.
   - `TEXT_SEARCH_PROVIDER=serper` (по умолчанию): Google через serper.dev.
   - `TEXT_SEARCH_PROVIDER=claude`: веб-поиск Claude. В выдачу попадают только ссылки, которые действительно вернул
     поиск; ссылку, придуманную моделью, SIFT отбрасывает.

Оба канала работают параллельно, один раз на поиск для всех площадок сразу. Дубликаты по ссылке убираются.
Карточки помечаются «по фото в Google» или «веб-поиск», а на экране результатов есть подсказка проверять цену
и наличие на сайте. Какие площадки обслуживаются так, задаёт `WEB_SEARCH_MARKETPLACES`. Как только у площадки
появляются официальные ключи или фид, SIFT автоматически переключается на них.

Ограничения: в индекс попадают не все свежие объявления, а объявление могло уже уйти. Это компромисс, пока
нет партнёрских API.

## Сводка

| Площадка | С ключами / фидом | Без них (веб-источники) |
|---|---|---|
| eBay | официальный Browse API, поиск по фото и тексту | ✅ Lens + веб-поиск |
| AliExpress | AliExpress Affiliate API | ✅ Lens + веб-поиск |
| Taobao | Taobao Union (淘宝联盟) TOP API | ✅ Lens + веб-поиск |
| Wildberries | лицензированный фид в pgvector | ✅ Lens + веб-поиск |
| Avito | легального API поиска нет | ✅ Lens + веб-поиск |
| Vinted | публичного API нет | ✅ Lens + веб-поиск |
| Grailed | публичного API нет | ✅ Lens + веб-поиск |
| Goofish (闲鱼) | отключено (`GOOFISH_ENABLED=false`) | отключено |

Статус каждой площадки в реальном времени: Mini App (чипы на экране результатов) и Админ-панель → «Интеграции».
Состояния: `active`, `not_configured` (нет ключей), `no_legal_api`, `disabled`, `down` (последняя
проверка здоровья не прошла; проверки идут каждые 10 минут, число ошибок подряд видно в админке). Если площадка
падает во время конкретного поиска, остальные продолжают работу, а у неё в результатах отображается «ошибка».

## eBay

1. Зарегистрируйтесь на [developer.ebay.com](https://developer.ebay.com) и создайте **Production keyset**.
2. `.env`:
   ```
   EBAY_CLIENT_ID=...
   EBAY_CLIENT_SECRET=...
   EBAY_MARKETPLACE_ID=EBAY_US      # EBAY_GB, EBAY_DE ...
   EBAY_CATEGORY_IDS=11450          # Clothing, Shoes & Accessories
   EBAY_IMAGE_SEARCH=true
   ```
3. Для партнёрских комиссий подключите [eBay Partner Network](https://partnernetwork.ebay.com) и укажите
   `EBAY_AFFILIATE_CAMPAIGN_ID`: ссылки станут партнёрскими.
4. `search_by_image` eBay помечает как experimental. Если для вашего keyset он недоступен, SIFT автоматически
   переходит на текстовый поиск (это видно в логах).
5. Лимиты Browse API: по умолчанию 5000 вызовов в сутки, увеличиваются через Application Growth Check.

## AliExpress

1. Аккаунт на [portals.aliexpress.com](https://portals.aliexpress.com) (Affiliate), получите **Tracking ID**.
2. На [openservice.aliexpress.com](https://openservice.aliexpress.com) создайте приложение типа Affiliate и
   дождитесь одобрения, затем получите App Key и App Secret.
3. `.env`: `ALIEXPRESS_APP_KEY`, `ALIEXPRESS_APP_SECRET`, `ALIEXPRESS_TRACKING_ID`, валюта, язык и страна доставки.
4. Используются методы `aliexpress.affiliate.product.query` и `aliexpress.affiliate.productdetail.get`. Ссылки
   в результатах являются официальными промо-ссылками.

## Taobao

1. Аккаунт [Taobao Union (pub.alimama.com)](https://pub.alimama.com), создайте рекламное место и получите **adzone_id**.
2. На [open.taobao.com](https://open.taobao.com) создайте приложение и получите App Key и Secret.
   Для регистрации обычно нужен аккаунт Taobao/Alipay с подтверждённой личностью.
3. `.env`: `TAOBAO_APP_KEY`, `TAOBAO_APP_SECRET`, `TAOBAO_ADZONE_ID`.
4. Метод: `taobao.tbk.dg.material.optional.upgrade`, запросы строятся на китайском. Цены приводятся
   в рубли/доллары по курсу ЦБ РФ (обновляется каждые 6 часов).

## Wildberries

У Wildberries нет публичного API поиска по чужим товарам: API продавца (`dev.wildberries.ru`) работает только
со своими карточками. Легальный путь только один: **партнёрский/аффилиатный фид** (через CPA-сеть или по прямому
договору). SIFT импортирует его в свою базу и ищет по нему визуально.

```bash
# YML (Яндекс.Маркет формат) по URL
docker compose exec worker python -m app.cli.feeds import --source wildberries --url https://partner.example/feed.yml --format yml
# или CSV: id,title,url,image_url,price,currency,brand,category,size,color,condition,available
docker compose exec worker python -m app.cli.feeds import --source wildberries --path /data/uploads/wb.csv --format csv
# посчитать эмбеддинги картинок (можно запускать повторно, считает только новые)
docker compose exec worker python -m app.cli.feeds embed --source wildberries --batch 64
```

Обновляйте фид по cron (например, раз в сутки). Пока фид не импортирован, Wildberries имеет статус
`not_configured`. Тот же механизм (`FeedCatalogProvider`) подходит для любой площадки, которая даст фид.

## Avito, Vinted, Grailed

| Площадка | Почему недоступна | Что нужно |
|---|---|---|
| Avito | API (developers.avito.ru) даёт доступ только к своим объявлениям, мессенджеру и автозагрузке; поиска по чужим нет; парсинг запрещён правилами | партнёрский договор или лицензированный фид |
| Vinted | публичного API нет; Vinted Pro Integrations только для продавцов | прямое партнёрство |
| Grailed | публичного API нет | прямое партнёрство |

Адаптеры уже есть в коде. Если появится партнёрский API или фид, реализуйте `search()` в
`backend/app/marketplace/providers/` или подключите площадку как фид, после чего она включится без изменений UI.

## Goofish (闲鱼)

Открытая платформа Goofish рассчитана на продавцов (публикация и управление своими лотами), поиска по чужим
объявлениям в ней нет. По решению владельца продукта площадка **отключена** и скрыта из приложения
(`GOOFISH_ENABLED=false`). Адаптер оставлен в коде на случай партнёрства.

## Добавить новую площадку

1. Класс-наследник `MarketplaceProvider` в `backend/app/marketplace/providers/`: методы `search`,
   `get_product`, `normalize_product` и при необходимости `check_availability`.
2. Регистрация в `app/marketplace/registry.py`.
3. Код площадки в `MARKETPLACES_ENABLED`.
