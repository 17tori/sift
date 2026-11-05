const SYMBOL: Record<string, string> = { RUB: "₽", USD: "$", EUR: "€", CNY: "¥", GBP: "£", KZT: "₸", XTR: "⭐" };

export function money(value: string | number | null | undefined, currency: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  const digits = n >= 1000 || Number.isInteger(n) ? 0 : 2;
  const s = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n);
  const sym = currency ? SYMBOL[currency] ?? currency : "";
  return currency === "USD" || currency === "GBP" || currency === "EUR" ? `${sym}${s}` : `${s} ${sym}`.trim();
}

export function num(n: number): string {
  return new Intl.NumberFormat("ru-RU").format(n);
}

export function date(iso: string, withTime = false): string {
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", withTime
    ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }
    : { day: "numeric", month: "long", year: "numeric" });
}

export function relative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} дн назад`;
  return date(iso);
}

export function timeLeft(iso: string): string {
  const s = Math.max(0, (new Date(iso).getTime() - Date.now()) / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d} дн ${h} ч`;
  if (h > 0) return `${h} ч ${m} мин`;
  return `${m} мин`;
}

export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

export const MODE_LABEL: Record<string, { title: string; hint: string }> = {
  exact: { title: "Точно", hint: "Та же вещь" },
  similar: { title: "Похожие", hint: "Близкие модели" },
  cheaper: { title: "Дешевле", hint: "Аналоги дешевле" },
  discover: { title: "Стиль", hint: "Альтернативы" },
};

export const CONDITION_LABEL: Record<string, string> = { new: "Новое", used: "Б/у", refurbished: "Восстановлено" };

export const CATEGORY_LABEL: Record<string, string> = {
  tops: "Верх", outerwear: "Верхняя одежда", dresses: "Платья", bottoms: "Низ", suits: "Костюмы",
  knitwear: "Трикотаж", activewear: "Спорт", underwear: "Бельё", shoes: "Обувь", bags: "Сумки",
  accessories: "Аксессуары", jewelry: "Украшения", watches: "Часы", eyewear: "Очки", headwear: "Головные уборы",
  other: "Другое",
};

export const ERROR_LABEL: Record<string, string> = {
  ai_unavailable: "AI-анализ временно недоступен. Поиск не списан, попробуйте позже.",
  not_a_product: "На фото не найден товар. Попробуйте снимок, где вещь видна крупно.",
  no_sources: "Сейчас нет подключённых площадок. Поиск не списан.",
  all_sources_failed: "Площадки не ответили. Поиск не списан, повторите попытку.",
  internal_error: "Внутренняя ошибка. Поиск не списан.",
  timeout: "Поиск занял слишком много времени. Поиск не списан.",
  cancelled: "Поиск был прерван. Поиск не списан.",
};
