# Установка и эксплуатация

Целевой сервер: Ubuntu 24.04, 4 vCPU, 8 GB RAM, 120 GB NVMe, свой домен. Лимиты в `docker-compose.yml`
рассчитаны на эту конфигурацию. Для 2 vCPU / 4 GB уменьшите `API_WORKERS=2`, `WORKER_PROCESSES=1`, `WORKER_THREADS=4`
и лимиты памяти Postgres и worker.

## 1. Подготовка

1. Создайте бота и Mini App ([BOTFATHER.md](BOTFATHER.md)). Понадобятся `BOT_TOKEN` и `BOT_USERNAME`.
2. Направьте A-запись домена на IP сервера и дождитесь, пока DNS обновится (`dig +short sift.example.com`).
3. Узнайте свой Telegram ID (например, через @userinfobot). Он нужен для доступа к админ-панели.
4. Получите ключи Gemini и serper.dev ([AI.md](AI.md)) и, по возможности, маркетплейсов ([MARKETPLACES.md](MARKETPLACES.md)).

## 2. Установка

```bash
ssh root@<ip>
git clone <repo> /opt/sift && cd /opt/sift
sudo DOMAIN=sift.example.com LETSENCRYPT_EMAIL=you@example.com \
     BOT_TOKEN=123456:ABC BOT_USERNAME=sift_bot ADMIN_TELEGRAM_IDS=123456789 \
     ./scripts/install.sh
```

`scripts/install.sh` идемпотентен, его можно запускать повторно. Что он делает:

- ставит Docker Engine и Compose plugin из официального репозитория Docker;
- открывает в ufw только 22, 80 и 443 (Postgres и Redis наружу не публикуются никогда);
- создаёт swap на 2 GB и включает автоматические обновления безопасности;
- создаёт `.env` из `.env.example` со случайными `SECRET_KEY`, `POSTGRES_PASSWORD` и `BOT_WEBHOOK_SECRET`;
- запускает `docker compose up -d --build`, ждёт готовности API и выпускает сертификат (`scripts/init-letsencrypt.sh`).

Потом откройте `.env` и заполните `GEMINI_API_KEY` и `SERPER_API_KEY` (этого достаточно для поиска по всем
площадкам), а позже ключи площадок, когда их одобрят. Примените изменения:

```bash
docker compose up -d
```

Проверка: `https://<домен>/healthz` возвращает `{"status":"ok"}`, а бот отвечает на /start.

## 3. Сервисы

| Сервис | Назначение | Лимит памяти |
|---|---|---|
| postgres | PostgreSQL 17 + pgvector (shared_buffers 1 GB) | 3 GB |
| redis | кэш, лимиты, брокер очередей (AOF) | 512 MB |
| migrate | `alembic upgrade head` перед стартом приложения | 256 MB |
| api | FastAPI, 4 воркера uvicorn | 1 GB |
| worker | Dramatiq, 2 процесса × 6 потоков: поиск (приоритетная и обычная очереди), обслуживание | 1.5 GB |
| scheduler | подписки, напоминания, триал, здоровье площадок, курсы ЦБ, ценовые алерты | 192 MB |
| bot | aiogram, polling или webhook | 256 MB |
| nginx | TLS, статика Mini App, лимиты запросов, прокси | 96 MB |
| certbot | продление сертификата дважды в сутки | 128 MB |
| backup | ежедневный `pg_dump` с проверкой и ротацией | 128 MB |

Всего около 6.8 GB под пиковую нагрузку, около 1 GB остаётся системе. Swap 2 GB страхует сборку образов.

## 4. Режим бота

- `BOT_MODE=polling` (по умолчанию) самый простой вариант, ничего настраивать не нужно.
- `BOT_MODE=webhook`: Telegram шлёт апдейты на `https://<домен>${BOT_WEBHOOK_PATH}`, nginx проксирует их в
  сервис bot, а `BOT_WEBHOOK_SECRET` проверяется в заголовке. Это быстрее и не держит long-poll соединение.

## 5. Обновление

```bash
cd /opt/sift && ./scripts/deploy.sh            # git pull, сборка, миграции, рестарт
REF=v1.2.0 ./scripts/deploy.sh                 # конкретный тег
```

Автодеплой из GitHub Actions описан в `.github/workflows/deploy.yml`. Он срабатывает на тег `v*` или запускается вручную.
Нужны секреты репозитория `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY` и `SSH_KNOWN_HOSTS`, плюс переменная `DEPLOY_PATH`.

## 6. Бэкапы

- Сервис `backup` каждый день в `BACKUP_HOUR_UTC` (по умолчанию 03:00 UTC) делает `pg_dump -Fc` в `./backups`,
  проверяет файл через `pg_restore --list` и удаляет копии старше `BACKUP_RETENTION_DAYS` (14 дней).
- Ручной бэкап: `./scripts/backup.sh`.
- Восстановление: `./scripts/restore.sh backups/sift-YYYYmmdd-HHMMSS.dump`. Скрипт сначала делает страховочный
  бэкап, останавливает приложение, восстанавливает базу в одной транзакции и поднимает сервисы.
- Копируйте бэкапы за пределы сервера, например в S3-совместимое хранилище через `rclone` по cron. Бэкап на том же
  диске не защищает от потери сервера.
- Загруженные фото лежат в volume `uploads` и удаляются через `UPLOAD_RETENTION_DAYS` дней, поэтому в бэкап не входят.

## 7. Мониторинг

- `docker compose ps`: статусы и healthcheck (api: `/readyz` проверяет БД и Redis; nginx: `/healthz`).
- `docker compose logs -f api worker bot`: JSON-логи, ротация 10 MB × 3 на сервис.
- Админ-панель → «Ошибки»: последние 1000 ошибок всех сервисов.
- Админ-панель → «Интеграции»: состояние каждой площадки и статистика AI.

## 8. Каталог Wildberries (лицензированный фид)

```bash
docker compose cp ./wb-feed.yml worker:/data/uploads/wb-feed.yml
docker compose exec worker python -m app.cli.feeds import --source wildberries --path /data/uploads/wb-feed.yml --format yml
docker compose exec worker python -m app.cli.feeds embed --source wildberries --batch 64
```

Подробнее в [MARKETPLACES.md](MARKETPLACES.md).

## 9. Частые проблемы

| Симптом | Причина |
|---|---|
| `init-letsencrypt.sh`: healthz недоступен | A-запись ещё не обновилась или порт 80 закрыт у хостера |
| Mini App показывает «откройте через бота» | открыта в браузере, а не через кнопку бота |
| Поиск завершается с «AI недоступен» | не заданы или неверны `GEMINI_API_KEY` и `SERPER_API_KEY` (см. `docker compose logs worker`) |
| Lens ничего не находит | `PUBLIC_BASE_URL` недоступен из интернета: serper.dev не может скачать фото |
| Площадка «не настроена» | не заполнены её ключи в `.env` |
| `migrate` падает | проверьте `DATABASE_URL`: пароль должен совпадать с `POSTGRES_PASSWORD` |
