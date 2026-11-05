# SIFT

**Одна фотография. Все маркетплейсы.** Telegram-бот и Mini App для визуального поиска товаров по фото.
Fashion-first: одежда, обувь, сумки, аксессуары.

Пользователь отправляет фото. AI определяет категорию, цвет, материал и силуэт и строит запросы на трёх языках.
Подключённые площадки ищут параллельно, а результаты ранжируются по визуальной близости (эмбеддинги изображений
в pgvector). Процент сходства показывается только тогда, когда его действительно посчитала модель.
Площадки без партнёрских ключей подключаются через Google Lens и поиск Google (serper.dev), без парсинга сайтов.

## Что внутри

| Компонент | Технологии |
|---|---|
| API | FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic 2 |
| База | PostgreSQL 17 + pgvector (HNSW, cosine) |
| Очереди | Redis 7 + Dramatiq (приоритетная очередь для PRO/ULTRA) |
| Бот | aiogram 3 (polling или webhook) |
| Mini App | React 19, TypeScript, Vite, Tailwind 4, Motion |
| AI и поиск | Gemini (анализ фото), serper.dev: Google Lens и Google; опционально Claude, Jina / Voyage |
| Платежи | Telegram Stars (XTR), включая рекуррентные подписки |
| Инфраструктура | Docker Compose, Nginx, Let's Encrypt, ежедневные бэкапы |

## Быстрый старт (VPS, Ubuntu 24.04)

```bash
git clone <repo> /opt/sift && cd /opt/sift
sudo DOMAIN=sift.example.com LETSENCRYPT_EMAIL=you@example.com \
     BOT_TOKEN=123456:ABC BOT_USERNAME=sift_bot ADMIN_TELEGRAM_IDS=123456789 \
     ./scripts/install.sh
```

Скрипт ставит Docker, файрвол и swap, генерирует секреты в `.env`, собирает и запускает стек и выпускает
TLS-сертификат. Ключи Gemini и serper.dev (и площадок, когда появятся) добавьте в `.env`, затем `docker compose up -d`.

Подробно: [docs/INSTALL.md](docs/INSTALL.md).

## Документация

- [INSTALL.md](docs/INSTALL.md): установка, обновление, бэкапы, мониторинг
- [BOTFATHER.md](docs/BOTFATHER.md): создание бота и настройка Mini App
- [PAYMENTS_STARS.md](docs/PAYMENTS_STARS.md): тарифы, Stars, подписки, возвраты, триал, рефералы
- [AI.md](docs/AI.md): провайдеры, калибровка процента сходства, стоимость
- [MARKETPLACES.md](docs/MARKETPLACES.md): статус каждой площадки и как подключить
- [ARCHITECTURE.md](docs/ARCHITECTURE.md): устройство системы, поток поиска, безопасность

## Разработка

```bash
# зависимости для тестов
docker run -d --name sift-pg -e POSTGRES_USER=sift -e POSTGRES_PASSWORD=sift -e POSTGRES_DB=sift_test -p 5432:5432 pgvector/pgvector:pg17
docker run -d --name sift-redis -p 6379:6379 redis:7.4-alpine

cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && pytest -q

cd ../frontend && npm ci && npm run dev   # http://localhost:5173, /api проксируется на :8000
```

В dev-режиме Mini App открывается и вне Telegram, но API всё равно требует подписанный `initData`.

## Брендинг

Название, слоганы, акцентный цвет и контакты поддержки задаются в `.env` (`BRAND_*`) без изменения кода.
