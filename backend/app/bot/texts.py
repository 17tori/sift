from __future__ import annotations

from html import escape

from app.core.config import get_settings


def welcome(first_name: str, trial_available: bool, trial_days: int, trial_started: bool) -> str:
    s = get_settings()
    lines = [
        f"<b>{escape(s.brand_name)}</b> · {escape(s.brand_tagline_ru)}",
        "",
        f"Привет, {escape(first_name or 'друг')}.",
        "Отправь фото вещи, которую увидел в Pinterest, Instagram или на улице, и я найду похожие "
        "предложения на маркетплейсах: точные совпадения, похожие модели и варианты дешевле.",
        "",
        "• поиск по фото с визуальным сходством",
        "• сравнение цен между площадками",
        "• избранное, история и уведомления о снижении цены",
    ]
    if trial_started:
        lines += ["", f"🎁 Пробный PRO на {trial_days} дн. уже активирован. Автосписаний нет."]
    elif trial_available:
        lines += ["", f"🎁 Доступен бесплатный PRO на {trial_days} дн. Без автосписания."]
    lines += ["", "Открой приложение или просто пришли фото сюда."]
    return "\n".join(lines)


HELP = (
    "<b>Как пользоваться</b>\n\n"
    "1. Открой приложение кнопкой ниже или командой /app.\n"
    "2. Загрузи фото вещи (JPG, PNG, WEBP, до 10 МБ) или пришли его прямо в чат.\n"
    "3. Выбери режим: точное совпадение, похожие, дешевле или альтернативы.\n"
    "4. Сравни цены и открой объявление на площадке.\n\n"
    "Процент сходства показывается только когда его посчитала модель визуального сравнения.\n\n"
    "/profile — профиль\n/subscription — подписка\n/history — история\n/support — поддержка"
)

STATUS_RU = {"completed": "готово", "failed": "ошибка", "running": "в процессе", "queued": "в очереди"}
