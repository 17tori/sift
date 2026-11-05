# Бот и Mini App в BotFather

## 1. Бот

1. Откройте [@BotFather](https://t.me/BotFather) и отправьте `/newbot`.
2. Задайте имя (например, `SIFT`) и username (например, `sift_search_bot`).
3. Сохраните токен в `.env`: `BOT_TOKEN=...` и `BOT_USERNAME=sift_search_bot` (без `@`).
4. Оформление: `/setdescription`, `/setabouttext`, `/setuserpic`.

Команды (`/start`, `/app`, `/profile`, `/subscription`, `/history`, `/help`, `/support`) и кнопка меню,
открывающая Mini App, регистрируются ботом автоматически при запуске. В BotFather их задавать не нужно.

## 2. Mini App

1. В @BotFather: `/newapp`, затем выберите бота.
2. Название, описание и картинка 640×360.
3. **Web App URL**: `https://<ваш-домен>/` (то же значение, что `WEBAPP_URL` в `.env`).
4. Короткое имя, например `app`. Ссылка на приложение будет `https://t.me/<bot>/app`.

Дополнительно в `/mybots` → бот → **Bot Settings**:
- **Configure Mini App → Enable Mini App**: тот же URL. Тогда приложение открывается из профиля бота.
- **Menu Button** бот выставляет сам. Если вы меняли её вручную, верните через `/setmenubutton`.

## 3. Deep links

| Ссылка | Что откроется |
|---|---|
| `https://t.me/<bot>?start=ref_<КОД>` | бот с реферальным кодом (код есть в Mini App → «Пригласить друзей») |
| `https://t.me/<bot>/app?startapp=search_<uuid>` | Mini App сразу на результатах поиска |
| `https://t.me/<bot>/app?startapp=subscription` | Mini App на экране подписки |

## 4. Платежи

Для Telegram Stars провайдер платежей в BotFather **не подключается**: Stars работают для цифровых товаров
без него. Подробнее в [PAYMENTS_STARS.md](PAYMENTS_STARS.md).

## 5. Безопасность

- Mini App получает `initData` от Telegram. Каждый запрос к API проверяется HMAC-подписью с ключом от
  `BOT_TOKEN` и сроком годности (`INIT_DATA_MAX_AGE_SECONDS`). Подделать пользователя без токена бота невозможно.
- Если токен утёк: `/revoke` в BotFather, новый токен в `.env`, затем `docker compose up -d`.
- Доступ к админ-панели есть только у ID из `ADMIN_TELEGRAM_IDS`, и он проверяется на сервере.
