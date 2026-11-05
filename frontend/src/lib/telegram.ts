/* Typed wrapper around the official Telegram Mini Apps SDK (telegram-web-app.js). */

type HapticStyle = "light" | "medium" | "heavy" | "rigid" | "soft";
type InvoiceStatus = "paid" | "cancelled" | "failed" | "pending";

interface TgWebApp {
  initData: string;
  initDataUnsafe: { user?: { id: number; first_name: string; username?: string; photo_url?: string }; start_param?: string };
  colorScheme: "light" | "dark";
  platform: string;
  version: string;
  isVersionAtLeast(v: string): boolean;
  ready(): void;
  expand(): void;
  setHeaderColor(c: string): void;
  setBackgroundColor(c: string): void;
  setBottomBarColor?(c: string): void;
  disableVerticalSwipes?(): void;
  openLink(url: string, opts?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  openInvoice(url: string, cb?: (status: InvoiceStatus) => void): void;
  showConfirm(msg: string, cb: (ok: boolean) => void): void;
  showAlert(msg: string, cb?: () => void): void;
  onEvent(e: string, cb: () => void): void;
  offEvent(e: string, cb: () => void): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void; offClick(cb: () => void): void };
  HapticFeedback: {
    impactOccurred(s: HapticStyle): void;
    notificationOccurred(t: "error" | "success" | "warning"): void;
    selectionChanged(): void;
  };
  safeAreaInset?: { top: number; bottom: number };
  contentSafeAreaInset?: { top: number; bottom: number };
}

declare global {
  interface Window {
    Telegram?: { WebApp: TgWebApp };
  }
}

export const tg: TgWebApp | null = typeof window !== "undefined" && window.Telegram?.WebApp?.initData ? window.Telegram.WebApp : null;

export const initData = (): string => tg?.initData ?? "";
export const startParam = (): string | undefined => tg?.initDataUnsafe.start_param;
export const insideTelegram = (): boolean => !!tg;

export function bootTelegram(): void {
  if (!tg) return;
  tg.ready();
  tg.expand();
  tg.disableVerticalSwipes?.();
  const applyInsets = () => {
    const top = (tg.safeAreaInset?.top ?? 0) + (tg.contentSafeAreaInset?.top ?? 0);
    const bottom = tg.safeAreaInset?.bottom ?? 0;
    document.documentElement.style.setProperty("--tg-safe-top", `${top}px`);
    document.documentElement.style.setProperty("--tg-safe-bottom", `${bottom}px`);
  };
  applyInsets();
  tg.onEvent("safeAreaChanged", applyInsets);
  tg.onEvent("contentSafeAreaChanged", applyInsets);
}

export function telegramScheme(): "light" | "dark" {
  if (tg) return tg.colorScheme;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function paintChrome(bg: string): void {
  if (!tg) return;
  try {
    tg.setHeaderColor(bg);
    tg.setBackgroundColor(bg);
    tg.setBottomBarColor?.(bg);
  } catch {
    /* older clients */
  }
}

export const haptic = {
  tap: () => tg?.HapticFeedback.impactOccurred("light"),
  select: () => tg?.HapticFeedback.selectionChanged(),
  success: () => tg?.HapticFeedback.notificationOccurred("success"),
  error: () => tg?.HapticFeedback.notificationOccurred("error"),
};

export function openExternal(url: string): void {
  if (tg) tg.openLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}

export function openTelegram(url: string): void {
  if (tg) tg.openTelegramLink(url);
  else window.open(url, "_blank", "noopener,noreferrer");
}

export function openInvoice(url: string): Promise<InvoiceStatus> {
  return new Promise((resolve) => {
    if (!tg) {
      window.open(url, "_blank");
      resolve("pending");
      return;
    }
    tg.openInvoice(url, (status) => resolve(status));
  });
}

export function confirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    if (tg && tg.isVersionAtLeast("6.2")) tg.showConfirm(message, resolve);
    else resolve(window.confirm(message));
  });
}

export function backButton(onBack: (() => void) | null): () => void {
  if (!tg) return () => undefined;
  if (!onBack) {
    tg.BackButton.hide();
    return () => undefined;
  }
  tg.BackButton.show();
  tg.BackButton.onClick(onBack);
  return () => {
    tg.BackButton.offClick(onBack);
  };
}
